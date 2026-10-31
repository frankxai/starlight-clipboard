"""Portable storage, retrieval and recovery for Starlight Clipboard. Standard library only."""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
import uuid

VERSION = "2026.10.31.4"
SCHEMA_VERSION = 2
STATES = {"active", "saved", "resolved", "archived"}
MUSIC = re.compile(r"(?i)\b(piano|strings|guitar|synth|orchestral|cinematic|ambient|lo-fi|techno|trance|house|drums|vocals?|instrumental|chorus|verse|suno)\b")
BPM = re.compile(r"(?i)\b(\d{2,3})\s*bpm\b")
STRUCTURE = re.compile(r"(?im)^\s*\[(intro|verse|chorus|bridge|outro|drop|instrumental)(?:[^\]]*)\]")
FILTER = re.compile(r'(?<!\S)(app|use|type|state|after|before|on|device):(?:"([^"]*)"|(\S+))')


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def migrate(conn: sqlite3.Connection, device: str) -> None:
    if conn.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION:
        return
    columns = {r[1] for r in conn.execute("PRAGMA table_info(clips)")}
    for name, declaration in (
        ("uid", "TEXT"), ("use_case", "TEXT NOT NULL DEFAULT ''"),
        ("state", "TEXT NOT NULL DEFAULT 'active'"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE clips ADD COLUMN {name} {declaration}")
    conn.execute("CREATE TABLE IF NOT EXISTS clip_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    conn.execute("INSERT OR IGNORE INTO clip_meta VALUES('store_id',?)", (uuid.uuid4().hex,))
    store_id = conn.execute("SELECT value FROM clip_meta WHERE key='store_id'").fetchone()[0]
    conn.execute("UPDATE clips SET uid=? || ':' || id WHERE uid IS NULL", (store_id,))
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS clips_uid ON clips(uid)")
    conn.execute("CREATE INDEX IF NOT EXISTS clips_library ON clips(state,use_case,id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS clip_occurrences(
        event_id TEXT PRIMARY KEY,clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
        captured_at TEXT NOT NULL,source_app TEXT,source_title TEXT,device TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS occurrence_dates ON clip_occurrences(clip_id,captured_at)")
    conn.execute("""INSERT OR IGNORE INTO clip_occurrences
        SELECT uid || ':initial',id,captured_at,source_app,source_title,device FROM clips""")
    conn.execute("""CREATE TABLE IF NOT EXISTS clip_jobs(
        clip_id INTEGER PRIMARY KEY REFERENCES clips(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt REAL NOT NULL DEFAULT 0,error TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS clip_images(
        clip_id INTEGER PRIMARY KEY REFERENCES clips(id) ON DELETE CASCADE,png BLOB NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS clip_promotions(
        clip_uid TEXT NOT NULL,destination TEXT NOT NULL,path TEXT NOT NULL,
        created_at TEXT NOT NULL,PRIMARY KEY(clip_uid,destination))""")
    # Historical hit counts do not identify individual dates. Preserve the aggregate,
    # and add only the one occurrence for which a source timestamp exists.
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


def annotation(text: str, title: str = "") -> dict:
    words = {m.group(0).lower() for m in MUSIC.finditer(text[:12000])}
    tempo = BPM.search(text[:12000])
    music_prompt = len(words) >= 2 and (tempo is not None or "," in text or STRUCTURE.search(text))
    if music_prompt:
        result = {"use_case": "suno", "reason": "Music style directions; Suno is a suggested use case.",
                  "provenance": "local-rule-v1", "submission": "unknown"}
        if tempo and 20 <= int(tempo[1]) <= 400:
            result["bpm"] = int(tempo[1])
        return result
    if "suno" in title.lower() and len(text.strip()) >= 12:
        return {"use_case": "suno", "reason": "Copied from a window mentioning Suno; use is unverified.",
                "provenance": "window-title-hint-v1", "submission": "unknown"}
    return {"use_case": "", "provenance": "local-rule-v1"}


def occurrence(conn, clip_id, captured_at, app, title, device):
    conn.execute("INSERT INTO clip_occurrences VALUES(?,?,?,?,?,?)",
                 (uuid.uuid4().hex, clip_id, captured_at, app, title, device))


def parse_query(query: str) -> tuple[str, dict]:
    filters = {}
    def take(match):
        key = match[1]
        if key in filters:
            raise ValueError(f"Use {key}: only once.")
        filters[key] = match[2] if match[2] is not None else match[3]
        return " "
    text = FILTER.sub(take, query)
    return " ".join(text.split()), filters


def local_day(value: str) -> str:
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Dates must use YYYY-MM-DD.") from None
    return day.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def query_rows(conn, query: str, kind: str | None = None, limit: int = 100):
    text, filters = parse_query(query)
    clauses, args = [], []
    state = filters.get("state")
    if state == "any":
        pass
    elif state:
        if state not in STATES:
            raise ValueError("State must be active, saved, resolved, archived or any.")
        clauses.append("c.state=?")
        args.append(state)
    elif not text:
        clauses.append("c.state NOT IN ('archived','resolved')")
    selected_kind = filters.get("type", kind)
    if selected_kind:
        clauses.append("c.kind=?")
        args.append(selected_kind)
    for key, fields in (("app", ["c.source_app","c.source_title"]),("device", ["c.device"]),("use", ["c.use_case"])):
        if filters.get(key):
            clauses.append("(" + " OR ".join(f"lower({field}) LIKE ? ESCAPE '\\'" for field in fields) + ")")
            value = filters[key].lower().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
            args.extend(["%" + value + "%"] * len(fields))
    dates, date_args = [], []
    if "on" in filters:
        if "after" in filters or "before" in filters:
            raise ValueError("Use on: or an after:/before: range.")
        day = datetime.strptime(filters["on"], "%Y-%m-%d")
        filters["after"] = day.strftime("%Y-%m-%d")
        filters["before"] = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    for key, comparison in (("after", ">="), ("before", "<")):
        if key in filters:
            dates.append(f"o.captured_at {comparison} ?")
            date_args.append(local_day(filters[key]))
    if dates:
        clauses.append("EXISTS(SELECT 1 FROM clip_occurrences o WHERE o.clip_id=c.id AND " + " AND ".join(dates) + ")")
        args.extend(date_args)
    if text:
        words = re.findall(r"[^\W_]+", text, flags=re.UNICODE)[:20]
        if words:
            clauses.append("c.id IN (SELECT rowid FROM clips_fts WHERE clips_fts MATCH ?)")
            args.append(" AND ".join('"' + word.replace('"','""') + '"*' for word in words))
        else:
            clauses.append("c.body LIKE ?")
            args.append("%" + text + "%")
    where = " AND ".join(clauses) or "1"
    return list(conn.execute(f"SELECT c.* FROM clips c WHERE {where} ORDER BY c.pinned DESC,c.last_seen_at DESC,c.id DESC LIMIT ?",
                             [*args, min(max(int(limit), 1), 1000)]))


def safe_vault(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    blocked = {"private", "private-vault", "universe"}
    if any(part.lower() in blocked or part.lower().endswith("-private-vault") for part in resolved.parts):
        raise ValueError("The sealed private vault cannot receive clipboard or MCP exports.")
    return resolved


def backup(root: Path, destination: Path | None = None) -> Path:
    database = root / "data" / "clips.sqlite"
    if not database.is_file():
        raise ValueError("No clipboard database exists to back up.")
    destination = destination or root / "backups"
    destination = destination.resolve()
    if destination == root.resolve() or destination == database.parent.resolve():
        raise ValueError("Choose a separate snapshot directory.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    folder = destination / f"{stamp}-{uuid.uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(folder / "clips.sqlite")) as target:
                source.backup(target)
                target.commit()
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("The backup did not pass SQLite integrity checks.")
        # New pictures live transactionally in SQLite; preserve legacy image files too.
        image_root = root / "data" / "images"
        if image_root.is_dir():
            (folder / "images").mkdir()
            for image in image_root.glob("*.png"):
                if image.is_symlink() or image.resolve().parent != image_root.resolve():
                    raise ValueError("A legacy image points outside its storage directory.")
                shutil.copy2(image, folder / "images" / image.name)
        files = {}
        for file in folder.rglob("*"):
            if file.is_file():
                files[file.relative_to(folder).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
        manifest = {"schema": "starlight.clipboard-backup.v1", "created_at": now(),
                    "app_version": VERSION, "files": files, "encrypted": False,
                    "privacy": "private-local", "state": "verified-snapshot"}
        atomic_text(folder / "manifest.json", json.dumps(manifest, indent=2) + "\n")
        atomic_text(root / "data" / "last-backup.json", json.dumps({"path": str(folder), "created_at": manifest["created_at"]}) + "\n")
        return folder
    except Exception:
        # Keep partial evidence for inspection. A missing manifest means incomplete.
        raise


def restore(snapshot: Path, target: Path) -> Path:
    snapshot, target = snapshot.resolve(), target.resolve()
    if target.exists():
        raise ValueError("Restore requires a new, absent directory; the live store is never overwritten.")
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "starlight.clipboard-backup.v1" or "clips.sqlite" not in manifest.get("files", {}):
        raise ValueError("Not a completed Clipboard snapshot.")
    validated = []
    for relative, digest in manifest["files"].items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or (relative != "clips.sqlite" and not re.fullmatch(r"images/[0-9]+\.png", relative)):
            raise ValueError("Unexpected snapshot path.")
        source = snapshot / rel
        if source.is_symlink() or not source.resolve().is_relative_to(snapshot):
            raise ValueError("Snapshot links are not accepted.")
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("Snapshot checksum mismatch.")
        validated.append((relative, source))
    with closing(sqlite3.connect((snapshot / "clips.sqlite").as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Snapshot database is not intact.")
    (target / "data").mkdir(parents=True)
    for relative, source in validated:
        dest = target / "data" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    with closing(sqlite3.connect(target / "data" / "clips.sqlite")) as conn:
        # Sidecars and absolute image references are disposable caches from the old machine.
        columns = {r[1] for r in conn.execute("PRAGMA table_info(clips)")}
        conn.execute("UPDATE clips SET sidecar=NULL")
        if "uid" in columns:
            conn.execute("UPDATE clip_jobs SET status='pending',next_attempt=0,error=NULL")
            conn.execute("INSERT OR IGNORE INTO clip_jobs(clip_id) SELECT id FROM clips WHERE body IS NOT NULL")
        conn.commit()
    return target


def export_jsonl(conn, destination: Path, query: str = "state:any") -> int:
    if destination.exists():
        raise ValueError("Export destination already exists; choose a new filename.")
    # Explicit snapshot export: no public projection and no secret event bodies.
    rows = query_rows(conn, query, limit=1000)
    if len(rows) == 1000:
        raise ValueError("Export exceeds the bounded query. Narrow it by date; use backup for the entire store.")
    lines = []
    for row in rows:
        if row["kind"] == "secret":
            continue
        lines.append(json.dumps({key: row[key] for key in ("uid","captured_at","last_seen_at","kind","source_app",
                     "source_title","device","use_case","state","body")}, ensure_ascii=False))
    atomic_text(destination, "\n".join(lines) + ("\n" if lines else ""))
    return len(lines)
