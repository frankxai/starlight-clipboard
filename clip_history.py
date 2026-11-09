"""Bounded, read-only Windows history retrieval and transactional archive import."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import clip_store

SCHEMA = "starlight.windows-history.v1"


def migrate(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS clip_history_events(
        event_key TEXT PRIMARY KEY,clip_id INTEGER REFERENCES clips(id),
        captured_at TEXT NOT NULL,content_sha256 TEXT NOT NULL,
        disposition TEXT NOT NULL)""")


def enabled(conn):
    row = conn.execute("SELECT value FROM clip_meta WHERE key='windows_history_enabled'").fetchone()
    return bool(row and row[0] == "true")


def configure(conn, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO clip_meta VALUES('windows_history_enabled',?)", ("true" if value else "false",))
    return {"enabled": value, "state": "enabled" if value else "disabled", "interval_seconds": 60}


def read_native(inspect=False, excluded_apps=(), sensitive_title_pattern=""):
    exe = Path(os.environ.get("WINDIR", "C:/Windows"))/"System32/WindowsPowerShell/v1.0/powershell.exe"
    arguments = [str(exe), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
        str(Path(__file__).with_name("windows_history.ps1")), "-Mode", "Inspect" if inspect else "Read"]
    if excluded_apps:
        # PowerShell -File array binding is unreliable across native argv; use a
        # single comma-separated list consumed as one parameter by the helper.
        arguments += ["-ExcludedApps", ",".join(sorted(excluded_apps))]
    if sensitive_title_pattern:
        arguments += ["-SensitiveTitlePattern", sensitive_title_pattern]
    result = subprocess.run(arguments,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if len(result.stdout) > 2_000_000:
        raise ValueError("Windows history exceeded its transport limit.")
    packet = json.loads(result.stdout.decode("utf-8-sig"))
    if result.returncode or packet.get("schema") != SCHEMA:
        raise ValueError("Windows history is unavailable; the archive is unchanged.")
    return packet


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Invalid Windows history date.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Windows history dates require a timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def apply(conn, packet, *, device, scrub, classify, excluded, preview=False):
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise ValueError("Invalid Windows history packet.")
    if packet.get("status") != "Success":
        return {"state": packet.get("status", "Unavailable"), "added": 0, "matched": 0, "already_seen": 0, "skipped": 0}
    records = packet.get("records")
    if not isinstance(records, list) or len(records) > 25 or len(json.dumps(packet, ensure_ascii=False).encode()) > 2_000_000:
        raise ValueError("Windows history exceeded its import limits.")
    prepared, identities = [], set()
    skipped = sum(v for v in packet.get("skipped", {}).values() if type(v) is int and v >= 0)
    for row in records:
        if not isinstance(row, dict) or set(row) != {"id", "captured_at", "text", "source_app", "protected"}:
            raise ValueError("Invalid Windows history entry.")
        key = row["id"]
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9{}:._-]{1,100}", key) or key in identities:
            raise ValueError("Invalid or repeated Windows history identity.")
        identities.add(key)
        if type(row["protected"]) is not bool:
            raise ValueError("Invalid Windows history protection marker.")
        app, body = row["source_app"], row["text"]
        if not isinstance(app, str) or len(app) > 200 or not isinstance(body, str) or len(body) > 100_000:
            raise ValueError("Invalid Windows history content bounds.")
        when = timestamp(row["captured_at"])
        if row["protected"] or not body.strip() or excluded(app, ""):
            skipped += 1
            continue
        # A history packet cannot carry a hidden HTML/image representation, and
        # credential-like text is skipped rather than reintroduced by import.
        if scrub(body)[1] or scrub(app)[1]:
            skipped += 1
            continue
        digest = hashlib.sha256(body.encode()).hexdigest()
        event = "winhist:" + hashlib.sha256((device+"\0"+key).encode()).hexdigest()
        prepared.append((event, body, digest, when, app))
    counts = {"state": "preview" if preview else "imported", "added": 0, "matched": 0, "already_seen": 0, "skipped": skipped}
    with conn:
        for event, body, digest, when, app in prepared:
            prior = conn.execute("SELECT content_sha256,captured_at FROM clip_history_events WHERE event_key=?", (event,)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise ValueError("A Windows history identity changed. Existing originals were retained.")
                if prior[1] == when:
                    counts["already_seen"] += 1
                    continue
                # Windows may retain an item's identity when equal text is copied
                # again. Keep that dated event without changing the first source.
                event += ":"+hashlib.sha256(when.encode()).hexdigest()[:24]
                dated = conn.execute("SELECT content_sha256,captured_at FROM clip_history_events WHERE event_key=?", (event,)).fetchone()
                if dated:
                    if tuple(dated) != (digest, when):
                        raise ValueError("A Windows history event changed. Existing originals were retained.")
                    counts["already_seen"] += 1
                    continue
            # Match only a nearby native capture on the observer PC. Equal text
            # copied on another day remains a separate historical event.
            match = conn.execute("""SELECT c.id FROM clips c WHERE c.sha256=? AND c.body=?
                AND EXISTS(SELECT 1 FROM clip_occurrences o WHERE o.clip_id=c.id AND o.device=?
                    AND abs(julianday(o.captured_at)-julianday(?))<=3.0/86400)
                ORDER BY c.id DESC LIMIT 1""", (digest, body, device, when)).fetchone()
            disposition = "matched" if match else "added"
            counts[disposition] += 1
            if preview:
                continue
            if match:
                clip_id = match[0]
            else:
                annotation = clip_store.annotation(body)
                kind = classify(body)
                if kind == "text" and annotation.get("use_case"):
                    kind = "prompt"
                title = "Windows clipboard history · original device unknown"
                source = app[:80] if app else "windows-history"
                metadata = dict(annotation, provenance="windows-clipboard-history", origin_device="unknown", observed_on=device)
                cur = conn.execute("""INSERT INTO clips(captured_at,last_seen_at,kind,source_app,source_title,
                    sha256,char_len,preview,body,extra_json,device,uid,use_case) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (when, when, kind, source, title, digest, len(body), re.sub(r"\s+", " ", body).strip()[:160], body,
                     json.dumps(metadata, ensure_ascii=False), device, event, annotation.get("use_case", "")))
                clip_id = cur.lastrowid
                conn.execute("INSERT INTO clips_fts(rowid,preview,body,source_app,source_title,kind) VALUES(?,?,?,?,?,?)",
                    (clip_id, re.sub(r"\s+", " ", body).strip()[:160], body, source, title, kind))
                conn.execute("INSERT INTO clip_occurrences VALUES(?,?,?,?,?,?)", (event, clip_id, when, source, title, device))
                if kind in {"prompt", "code"}:
                    conn.execute("INSERT INTO clip_jobs(clip_id) VALUES(?)", (clip_id,))
            conn.execute("INSERT INTO clip_history_events VALUES(?,?,?,?,?)", (event, clip_id, when, digest, disposition))
    return counts


def status(root):
    path = Path(root)/"data/windows-history.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "not-scanned", "checked_at": None}


def enough_memory():
    # The helper's small reserve is in addition to the machine's Windows floor.
    import ctypes
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    return bool(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))) and memory.available >= (4096+256)*1024*1024
