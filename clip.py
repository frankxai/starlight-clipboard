"""Local clipboard index. Copies stay on this PC. Secret values are not stored."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import html
import json
import os
import re
import secrets
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import uuid
import clip_store
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

def starlight_dir(*parts: str) -> Path:
    home = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home).joinpath(".starlight", *parts)
FABRIC_BOOKS = {
    "frank": "frank-operating-voice",
    "starlight": "starlight-operations",
    "arcanea": "arcanea-studio",
    "frankx": "frankx-commercial",
    "general": "general",
}
MUTEX_NAME = "Local\\StarlightClipboardIndex"
MAX_READ = 1_000_000
MAX_CHARS = MAX_READ
PREVIEW_CHARS = 240
KEEP_DAYS = 90
MAX_ROWS = 20_000
POLL_SECONDS = 0.35

CF_UNICODETEXT = 13
CF_HDROP = 15
CF_DIB = 8
CF_DIBV5 = 17
GMEM_MOVEABLE = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000

SENSITIVE_APPS = {
    "bitwarden.exe",
    "keepass.exe",
    "keepassxc.exe",
    "1password.exe",
    "lastpass.exe",
    "dashlane.exe",
    "nordpass.exe",
    "credentialuibroker.exe",
}
SENSITIVE_TITLE = re.compile(
    r"(?i)\b(bitwarden|keepass|1password|lastpass|dashlane|nordpass|credential manager|windows security)\b"
)
OWNER_NOISE = {
    "python.exe",
    "pythonw.exe",
    "textinputhost.exe",
    "svchost.exe",
    "runtimebroker.exe",
    "applicationframehost.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "lockapp.exe",
    "dllhost.exe",
    "pickerhost.exe",
}
APP_NAMES = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "windowsterminal.exe": "Terminal",
    "code.exe": "VS Code",
    "cursor.exe": "Cursor",
    "notepad.exe": "Notepad",
    "snippingtool.exe": "Snip",
    "screenclippinghost.exe": "Snip",
    "explorer.exe": "Explorer",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "slack.exe": "Slack",
    "discord.exe": "Discord",
    "telegram.exe": "Telegram",
    "whatsapp.exe": "WhatsApp",
    "outlook.exe": "Outlook",
}

PROMPT_LINE = re.compile(
    r"(?im)^\s*(you are|act as|your (?:job|task|role) is|system prompt|instructions?:)\b"
)
ROLE_LINE = re.compile(r"(?im)^(system|user|assistant|developer)\s*:")
INSTRUCTION_WORDS = re.compile(
    r"(?i)\b(must|do not|don't|output|format|return only|step by step|write|generate|explain)\b"
)
CODE_HEAD = re.compile(
    r"(?i)^(import |from |def |class |function |const |let |var |fn |pub fn |#include |package |using |select |with )"
)
COMMAND_LINE = re.compile(
    r"(?i)^(git|pnpm|npm|npx|uv|py|python|pythonw|pwsh|powershell|docker|podman|gh|node|bun|cargo|go|curl|ssh|rg|claude|codex|grok)\s+\S"
)
URL_LINE = re.compile(r"https?://\S+")
PATH_LINE = re.compile(r"[A-Za-z]:\\[^<>:\"|?*\r\n]+")
REDACTION_TOKEN = re.compile(r"\[redacted:[a-z0-9-]+\]", re.I)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.argtypes = []
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetClipboardOwner.argtypes = []
user32.GetClipboardOwner.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT

kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenMutexW.restype = wintypes.HANDLE
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.SetLastError.argtypes = [wintypes.DWORD]
kernel32.SetLastError.restype = None

shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT

_MUTEX: wintypes.HANDLE | None = None
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] | None = None


def _j(*parts: str) -> str:
    return "".join(parts)


def secret_patterns() -> list[tuple[str, re.Pattern[str]]]:
    global _SECRET_PATTERNS
    if _SECRET_PATTERNS is not None:
        return _SECRET_PATTERNS
    long = r"[A-Za-z0-9_\-]{20,}"
    sk = _j("s", "k-")
    dashes = "-" * 5
    private_key = _j("PRI", "VATE KEY")
    begin = dashes + "BEGIN [A-Z ]*" + private_key + dashes
    end = dashes + "END [A-Z ]*" + private_key + dashes
    assignment_name = _j(
        r"(?:api[_-]?key|access[_-]?",
        "to",
        r"ken|auth[_-]?to",
        "ken|se",
        "cret|pass",
        "word|pass",
        "wd)",
    )
    patterns = [
        ("private-key", re.compile(begin + r"[\s\S]*?" + end)),
        ("anthropic", re.compile(r"\b" + sk + r"ant-" + r"[A-Za-z0-9_\-]{10,}\b")),
        ("openai", re.compile(r"\b" + sk + r"(?!ant-)" + long + r"\b")),
        ("openrouter", re.compile(r"\b" + sk + r"or-v1-[A-Za-z0-9]{20,}\b")),
        ("github-fine", re.compile(r"\b" + _j("github_", "pat_") + r"[A-Za-z0-9_]{20,}\b")),
        ("github", re.compile(r"\b" + _j("gh", "[pousr]_") + r"[A-Za-z0-9_]{20,}\b")),
        ("aws", re.compile(r"\b" + _j("AK", "IA") + r"[0-9A-Z]{16}\b")),
        ("google", re.compile(r"\b" + _j("AI", "za") + r"[0-9A-Za-z_\-]{35}\b")),
        ("slack", re.compile(r"\b" + _j("xo", "x") + r"[baprs]-[A-Za-z0-9-]{10,}\b")),
        ("stripe", re.compile(r"\b" + _j("(?:sk|rk)_live_") + r"[A-Za-z0-9]{16,}\b")),
        ("huggingface", re.compile(r"\b" + _j("h", "f_") + r"[A-Za-z0-9]{20,}\b")),
        ("npm", re.compile(r"\b" + _j("np", "m_") + r"[A-Za-z0-9]{36}\b")),
        ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}={0,2}")),
        ("assignment", re.compile(r"(?i)\b" + assignment_name + r"\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+]{8,}")),
    ]
    _SECRET_PATTERNS = patterns
    return patterns


def paths() -> dict[str, Path]:
    root = Path(os.environ["CLIP_HOME"]) if os.environ.get("CLIP_HOME") else starlight_dir("clipboard-index")
    data = root / "data"
    return {
        "root": root,
        "data": data,
        "db": data / "clips.sqlite",
        "prompts": root / "prompts",
        "snippets": root / "snippets",
        "logs": root / "logs" / "clipd.log",
        "stop": data / "stop.flag",
        "suppress": data / "suppress.txt",
    }


def emit(line: str = "") -> None:
    stream = sys.stdout
    if stream is None:
        return
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        stream.write(line + "\n")
    except UnicodeEncodeError:
        safe = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
        stream.write(safe + "\n")


def log(message: str) -> None:
    path = paths()["logs"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 1_000_000:
        backup = path.with_suffix(".log.1")
        if backup.exists():
            backup.unlink()
        path.replace(backup)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_time(iso: str) -> str:
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return iso[:16]
    return when.strftime("%Y-%m-%d %H:%M")


def connect() -> sqlite3.Connection:
    location = paths()
    location["data"].mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(location["db"], timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=4000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS clips (
          id INTEGER PRIMARY KEY,
          captured_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          kind TEXT NOT NULL,
          source_app TEXT,
          source_title TEXT,
          sha256 TEXT NOT NULL,
          char_len INTEGER NOT NULL,
          hit_count INTEGER NOT NULL DEFAULT 1,
          pinned INTEGER NOT NULL DEFAULT 0,
          preview TEXT NOT NULL,
          body TEXT,
          sidecar TEXT,
          extra_json TEXT
        );
        CREATE INDEX IF NOT EXISTS clips_sha ON clips(sha256);
        CREATE INDEX IF NOT EXISTS clips_kind_id ON clips(kind, id DESC);
        CREATE VIRTUAL TABLE IF NOT EXISTS clips_fts USING fts5(
          preview, body, source_app, source_title, kind,
          tokenize='unicode61'
        );
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
    if "device" not in columns:
        conn.execute("ALTER TABLE clips ADD COLUMN device TEXT")
    conn.execute("UPDATE clips SET device = ? WHERE device IS NULL OR device = ''", (this_device(),))
    conn.commit()
    clip_store.migrate(conn, this_device())


def redact(text: str) -> tuple[str, list[str]]:
    labels: list[str] = []

    def swap(label: str):
        def replace(_match: re.Match[str]) -> str:
            labels.append(label)
            return f"[redacted:{label}]"

        return replace

    cleaned = text
    for label, pattern in secret_patterns():
        cleaned = pattern.sub(swap(label), cleaned)
    return cleaned, labels


def only_redactions(text: str) -> bool:
    return REDACTION_TOKEN.sub("", text).strip() == ""


def prompt_reason(text: str) -> str | None:
    music = clip_store.annotation(text)
    if music.get("use_case"):
        return music["reason"]
    if PROMPT_LINE.search(text):
        return "It opens like an instruction to an agent."
    if ROLE_LINE.search(text):
        return "It names a system, user, or assistant role."
    if len(text) >= 280 and len(INSTRUCTION_WORDS.findall(text)) >= 2:
        return "It is long and written as directions."
    return None


def looks_like_prompt(text: str) -> bool:
    return prompt_reason(text) is not None


def looks_like_code(text: str) -> bool:
    if text.lstrip().startswith("```"):
        return True
    head = text.lstrip()[:120]
    if CODE_HEAD.match(head):
        return True
    if text.count("\n") >= 3:
        symbols = text.count("{") + text.count("}") + text.count(";")
        if symbols >= 4:
            return True
    return False


def classify_text(text: str) -> str:
    stripped = text.strip()
    if "\n" not in stripped and URL_LINE.fullmatch(stripped):
        return "url"
    if "\n" not in stripped and (PATH_LINE.fullmatch(stripped.strip('"')) or stripped.startswith("\\\\")):
        return "path"
    if "\n" not in stripped and COMMAND_LINE.match(stripped):
        return "command"
    if looks_like_prompt(text):
        return "prompt"
    if looks_like_code(text):
        return "code"
    return "text"


def sensitive_source(app: str, title: str) -> bool:
    if app.lower() in SENSITIVE_APPS:
        return True
    return bool(SENSITIVE_TITLE.search(title or ""))


def preview_of(text: str) -> str:
    one = re.sub(r"\s+", " ", text).strip()
    if len(one) <= PREVIEW_CHARS:
        return one
    return one[: PREVIEW_CHARS - 3] + "..."


def quote_yaml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_sidecar(kind: str, clip_id: int, captured_at: str, app: str, title: str, body: str, labels: list[str]) -> str:
    when = datetime.fromisoformat(captured_at.replace("Z", "+00:00")).astimezone()
    folder_name = "prompts" if kind == "prompt" else "snippets"
    folder = paths()[folder_name] / when.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{clip_id}.md"
    header = "\n".join(
        [
            "---",
            f"kind: {kind}",
            f"id: {clip_id}",
            f"captured_at: {quote_yaml(captured_at)}",
            f"source_app: {quote_yaml(app)}",
            f"source_title: {quote_yaml(title)}",
            f"chars: {len(body)}",
            "redactions: [" + ", ".join(quote_yaml(label) for label in labels) + "]",
            "---",
            "",
            body,
            "",
        ]
    )
    temporary = target.with_suffix(".md.tmp")
    temporary.write_text(header, encoding="utf-8")
    temporary.replace(target)
    return str(target)


def this_device() -> str:
    return os.environ.get("COMPUTERNAME") or "This PC"


def clip_device(app: str, device: str | None = None) -> str:
    if device:
        return device[:80]
    if (app or "").lower() in {"phoneexperiencehost.exe", "yourphone.exe"}:
        return "Phone"
    return this_device()


def device_roots() -> tuple[Path, Path]:
    root = paths()["root"] / "devices"
    out = root / "out"
    peers = root / "peers"
    out.mkdir(parents=True, exist_ok=True)
    peers.mkdir(parents=True, exist_ok=True)
    return out, peers


def export_device() -> None:
    conn = connect()
    try:
        init_db(conn)
        rows = list(
            conn.execute(
                """
                SELECT device, captured_at, kind, source_app, source_title, preview, body, sha256
                FROM clips
                WHERE kind != 'secret' AND body IS NOT NULL
                ORDER BY id DESC
                LIMIT 200
                """
            )
        )
    finally:
        conn.close()
    safe = re.sub(r"[^A-Za-z0-9.-]", "-", this_device()).strip("-") or "this-pc"
    path = device_roots()[0] / f"{safe}.jsonl"
    lines = [
        json.dumps({key: row[key] for key in row.keys()}, ensure_ascii=False)
        for row in reversed(rows)
    ]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def import_peers() -> int:
    added = 0
    _, peers = device_roots()
    conn = connect()
    try:
        init_db(conn)
        known = {row[0] for row in conn.execute("SELECT sha256 FROM clips")}
    finally:
        conn.close()
    for path in peers.glob("*.jsonl"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines[-200:]:
            if len(line) > 300_000:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            body = item.get("body") or ""
            if not body or item.get("kind") == "secret":
                continue
            if item.get("device") == this_device():
                continue
            redacted, _labels = redact(body)
            digest = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
            if digest in known:
                continue
            result = ingest(
                body,
                app=str(item.get("source_app") or ""),
                title=str(item.get("source_title") or ""),
                device=str(item.get("device") or "Peer"),
            )
            if result and not result.get("duplicate"):
                known.add(digest)
                added += 1
    return added


def ingest(text: str | None, *, app: str = "", title: str = "", files: list[str] | None = None,
           has_image: bool = False, device: str | None = None, html_bytes: bytes | None = None,
           png_bytes: bytes | None = None) -> dict | None:
    raw = (text or "").replace("\x00", "")
    files = files or []
    if not raw.strip() and not files and not has_image:
        return None
    truncated = len(raw) > MAX_READ
    raw = raw[:MAX_READ]
    title = redact(title)[0][:200]
    labels: list[str] = []
    body = None
    png_bytes = trim_png(png_bytes) if png_bytes else None
    if sensitive_source(app, title):
        kind, labels = "secret", ["vault-app"]
        png_bytes, files, html_bytes = None, [], None
    elif raw.strip():
        body, labels = redact(raw)
        if labels:
            html_bytes, png_bytes = None, None
        if labels and only_redactions(body):
            kind, body = "secret", None
        else:
            kind = classify_text(body)
    elif files:
        kind, body = "files", redact("\n".join(files[:100]))[0]
    else:
        kind = "image"
    annotation = clip_store.annotation(body or "", title)
    if kind == "text" and annotation.get("use_case"):
        kind = "prompt"
    if kind == "secret":
        preview, digest = "[redacted]", uuid.uuid4().hex
        app, title = "", ""
    elif kind == "image":
        preview = "Picture" if png_bytes else "Picture format unavailable"
        digest = hashlib.sha256(png_bytes).hexdigest() if png_bytes else uuid.uuid4().hex
    else:
        preview = preview_of(body or "")
        digest = hashlib.sha256(((body or "") + ("|image:" + hashlib.sha256(png_bytes).hexdigest() if png_bytes else "")).encode()).hexdigest()
    extra = dict(annotation)
    if labels:
        extra["redactions"] = labels
    if truncated:
        extra["truncated"] = True
        extra["capture_limit"] = MAX_READ
    if kind == "prompt":
        extra["reason"] = annotation.get("reason") or prompt_reason(body or "")
    if html_bytes and not labels and kind not in {"secret", "image"} and len(html_bytes) <= 120_000:
        # Recheck HTML independently: its hidden attributes can contain credentials.
        html_text = html_bytes.decode("utf-8", errors="replace")
        if not redact(html_text)[1]:
            extra["html_b64"] = __import__("base64").b64encode(html_bytes).decode("ascii")
    captured_at = clip_store.now()
    device_name = clip_device(app, device)
    conn = connect()
    try:
        init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        last = conn.execute("SELECT id,sha256,hit_count FROM clips ORDER BY id DESC LIMIT 1").fetchone()
        if last and last["sha256"] == digest:
            clip_id = int(last["id"])
            conn.execute("UPDATE clips SET hit_count=hit_count+1,last_seen_at=? WHERE id=?", (captured_at, clip_id))
            clip_store.occurrence(conn, clip_id, captured_at, app, title, device_name)
            conn.commit()
            return {"id": clip_id, "duplicate": True, "kind": kind}
        cursor = conn.execute("""INSERT INTO clips(
            captured_at,last_seen_at,kind,source_app,source_title,sha256,char_len,preview,body,
            extra_json,device,uid,use_case) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (captured_at,captured_at,kind,app[:80],title,digest,len(body or ""),preview,body,
             json.dumps(extra,ensure_ascii=False),device_name,uuid.uuid4().hex,annotation.get("use_case","")))
        clip_id = int(cursor.lastrowid)
        conn.execute("INSERT INTO clips_fts(rowid,preview,body,source_app,source_title,kind) VALUES(?,?,?,?,?,?)",
                     (clip_id,preview,body or "",app[:80],title,kind))
        clip_store.occurrence(conn, clip_id, captured_at, app, title, device_name)
        if png_bytes and kind != "secret":
            conn.execute("INSERT INTO clip_images VALUES(?,?)", (clip_id,png_bytes))
        if (body and kind in {"prompt","code"}) or png_bytes:
            conn.execute("INSERT INTO clip_jobs(clip_id) VALUES(?)", (clip_id,))
        conn.commit()
        return {"id":clip_id,"duplicate":False,"kind":kind,"chars":len(body or "")}
    finally:
        conn.close()


def prune(conn: sqlite3.Connection) -> int:
    """History is retained. Archive affects visibility, never automatic deletion."""
    return 0


def process_pending(limit: int = 8) -> int:
    conn = connect()
    done = 0
    try:
        init_db(conn)
        jobs = list(conn.execute("""SELECT c.* FROM clip_jobs j JOIN clips c ON c.id=j.clip_id
            WHERE j.status='pending' AND j.next_attempt<=? ORDER BY c.id LIMIT ?""", (time.time(),limit)))
        for row in jobs:
            try:
                sidecar = row["sidecar"]
                if row["body"] and row["kind"] in {"prompt","code"}:
                    sidecar = write_sidecar(row["kind"],row["id"],row["captured_at"],row["source_app"] or "",
                                            row["source_title"] or "",row["body"],json.loads(row["extra_json"] or "{}").get("redactions",[]))
                image = conn.execute("SELECT png FROM clip_images WHERE clip_id=?", (row["id"],)).fetchone()
                if image:
                    folder = paths()["data"] / "images"
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / f"{row['id']}.png"
                    temporary = target.with_suffix(".png.tmp")
                    with temporary.open("wb") as handle:
                        handle.write(image[0])
                        handle.flush()
                        os.fsync(handle.fileno())
                    temporary.replace(target)
                conn.execute("UPDATE clips SET sidecar=? WHERE id=?", (sidecar,row["id"]))
                conn.execute("UPDATE clip_jobs SET status='done',error=NULL WHERE clip_id=?", (row["id"],))
                conn.commit()
                done += 1
            except (OSError,ValueError,sqlite3.Error):
                conn.rollback()
                conn.execute("""UPDATE clip_jobs SET attempts=attempts+1,error='export-failed',
                    next_attempt=? WHERE clip_id=?""", (time.time()+60,row["id"]))
                conn.commit()
    finally:
        conn.close()
    return done


def set_state(clip_id: int, state: str) -> int:
    if state not in clip_store.STATES:
        raise ValueError("Unknown library state.")
    conn = connect()
    try:
        init_db(conn)
        found = conn.execute("UPDATE clips SET state=? WHERE id=?", (state,clip_id)).rowcount
        conn.commit()
        return 0 if found else 1
    finally:
        conn.close()


def reindex_library() -> int:
    conn = connect()
    updated = 0
    try:
        init_db(conn)
        for row in list(conn.execute("SELECT * FROM clips WHERE body IS NOT NULL AND kind!='secret'")):
            body, labels = redact(row["body"])
            extra = json.loads(row["extra_json"] or "{}")
            encoded = extra.get("html_b64")
            if encoded:
                try:
                    html_text = __import__("base64").b64decode(encoded, validate=True).decode("utf-8",errors="replace")
                    if labels or extra.get("redactions") or redact(html_text)[1]:
                        extra.pop("html_b64",None)
                except (ValueError,TypeError):
                    extra.pop("html_b64",None)
            annotation = clip_store.annotation(body,row["source_title"] or "")
            extra.update(annotation)
            kind = classify_text(body)
            if kind == "text" and annotation.get("use_case"):
                kind = "prompt"
            conn.execute("UPDATE clips SET body=?,preview=?,kind=?,use_case=?,extra_json=? WHERE id=?",
                         (body,preview_of(body),kind,annotation.get("use_case",""),json.dumps(extra),row["id"]))
            conn.execute("UPDATE clips_fts SET body=?,preview=?,kind=? WHERE rowid=?", (body,preview_of(body),kind,row["id"]))
            if kind in {"prompt","code"}:
                conn.execute("""INSERT INTO clip_jobs(clip_id) VALUES(?)
                    ON CONFLICT(clip_id) DO UPDATE SET status='pending',next_attempt=0""", (row["id"],))
            updated += 1
        conn.commit()
    finally:
        conn.close()
    return updated


def window_source(hwnd: int) -> tuple[str, str]:
    if not hwnd:
        return "", ""
    length = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if length > 0:
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value[:200]
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    app = ""
    if pid.value:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if handle:
            try:
                size = wintypes.DWORD(32768)
                name = ctypes.create_unicode_buffer(32768)
                if kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
                    app = os.path.basename(name.value)
            finally:
                kernel32.CloseHandle(handle)
    return app, title


def display_app(app: str) -> str:
    raw = (app or "").strip()
    if not raw:
        return ""
    mapped = APP_NAMES.get(raw.lower())
    if mapped:
        return mapped
    if raw.lower().endswith(".exe"):
        raw = raw[:-4]
    return raw[:1].upper() + raw[1:] if raw else ""


def clean_title(app: str, title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title or "").strip()
    for suffix in (
        " - Google Chrome",
        " - Microsoft Edge",
        " - Mozilla Firefox",
        " - Visual Studio Code",
        " - Cursor",
        " - Windows Terminal",
        " - Notepad",
    ):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    if not cleaned or cleaned.lower() in {app.lower(), display_app(app).lower()}:
        return ""
    return cleaned[:72]


def choose_app(owner_app: str, owner_title: str, fallback_app: str, fallback_title: str) -> tuple[str, str]:
    app = owner_app or ""
    title = owner_title or ""
    if not app or app.lower() in OWNER_NOISE:
        app, title = fallback_app or "", fallback_title or ""
    if app.lower() in OWNER_NOISE:
        return "", ""
    return app, title


TERMINAL_HOSTS = {
    "windowsterminal.exe",
    "windowsterminalpreview.exe",
    "openconsole.exe",
    "conhost.exe",
    "wt.exe",
}
_BOX_DRAWING = re.compile(r"[│┌┐└┘├┤┬┴┼╔╗╚╝║═╭╮╯╰]")
_DIFF_LINE = re.compile(r"^(diff |index |@@|\+\+\+|---|\+[^+]|\-[^-])")


def terminal_host(app: str) -> bool:
    return (app or "").lower() in TERMINAL_HOSTS


def _terminal_prose(text: str) -> bool:
    sample = text[:8000]
    if len(sample) < 40:
        return False
    letters = sum(ch.isalpha() for ch in sample)
    spaces = sample.count(" ")
    symbols = sum(sample.count(ch) for ch in "{}[]();=<>`")
    return letters >= len(sample) * 0.45 and spaces >= len(sample) * 0.08 and symbols <= len(sample) * 0.04


def _terminal_structured(lines: list[str]) -> bool:
    nonempty = [line for line in lines if line.strip()]
    if not nonempty or looks_like_code("\n".join(nonempty)):
        return True
    if any(line.lstrip().startswith("```") for line in nonempty):
        return True
    if sum(1 for line in nonempty if _BOX_DRAWING.search(line)) / len(nonempty) > 0.15:
        return True
    if sum(1 for line in nonempty if _DIFF_LINE.match(line.lstrip())) / len(nonempty) > 0.3:
        return True
    return False


def _join_wrapped(left: str, right: str) -> str:
    left = left.rstrip()
    right = right.strip()
    if not right:
        return left
    last = left[-1]
    first = right[0]
    if last == "-" and first.isalpha():
        return left + right
    token = 0
    for ch in reversed(left):
        if ch.isspace():
            break
        token += 1
    if token <= 2 and last.isalpha() and first.islower():
        return left + right
    return left + " " + right


def _keeps_break(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return True
    if stripped[0] in "-*#>" or stripped.startswith("```"):
        return True
    return bool(re.match(r"\d+[.)]\s", stripped))


def unwrap_terminal_wrap(text: str) -> str:
    """Rejoin lines a terminal painted at the window edge. Keep real paragraphs and code."""
    if not text or len(text) > 400_000 or "\n" not in text and "\r" not in text:
        return text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    had_trailing_newline = normalized.endswith("\n")
    raw_lines = normalized.split("\n")
    if had_trailing_newline and raw_lines and raw_lines[-1] == "":
        raw_lines = raw_lines[:-1]
    if len(raw_lines) < 2:
        return text
    lines = [line.rstrip() for line in raw_lines]
    nonempty = [line for line in lines if line.strip()]
    if len(nonempty) < 2 or _terminal_structured(lines) or not _terminal_prose("\n".join(nonempty)):
        return text
    max_len = max(len(line) for line in nonempty)
    if max_len < 64 or max_len > 320:
        return text
    # Word wrap stops before the margin, so the painted edge is a band, not one column.
    slack = min(18, max(8, max_len // 8))

    def is_full(line: str) -> bool:
        return bool(line.strip()) and len(line.rstrip()) >= max_len - slack

    full = [line for line in nonempty if is_full(line)]
    mid_sentence_pair = (
        len(nonempty) == 2
        and len(full) == 1
        and is_full(nonempty[0])
        and len(nonempty[1]) <= int(len(nonempty[0]) * 0.75)
        and nonempty[0][-1] not in ".!?:;"
        and nonempty[1].lstrip()[:1].islower()
    )
    if len(full) < 2 and not mid_sentence_pair:
        return text

    joined: list[str] = []
    pending: str | None = None
    pending_full = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            nxt = next((item for item in lines[index + 1 :] if item.strip()), None)
            if (
                pending_full
                and nxt is not None
                and not _keeps_break(nxt)
                and nxt.lstrip()[:1].islower()
            ):
                index += 1
                continue
            if pending is not None:
                joined.append(pending)
                pending = None
                pending_full = False
            if not joined or joined[-1] != "":
                joined.append("")
            index += 1
            continue
        if pending is None:
            pending = line
            pending_full = is_full(line)
        elif pending_full and not _keeps_break(line):
            pending = _join_wrapped(pending, line)
            pending_full = is_full(line)
        else:
            joined.append(pending)
            pending = line
            pending_full = is_full(line)
        index += 1
    if pending is not None:
        joined.append(pending)
    while joined and joined[-1] == "":
        joined.pop()
    result = "\n".join(joined)
    if had_trailing_newline:
        result += "\n"
    original = [line.rstrip() for line in normalized.split("\n")]
    repaired = [line.rstrip() for line in result.split("\n")]
    if original == repaired:
        return text
    return result


def repair_terminal_clipboard(fallback_app: str = "") -> bool:
    if own_paste_pending():
        return False
    snapshot = read_clipboard()
    if snapshot is None:
        return False
    text = snapshot.get("text") or ""
    if not text.strip() or snapshot.get("files") or snapshot.get("png") or snapshot.get("dib"):
        return False
    app, _title = choose_app(snapshot.get("app") or "", snapshot.get("title") or "", fallback_app, "")
    if not (terminal_host(app) or terminal_host(snapshot.get("app") or "") or terminal_host(fallback_app)):
        return False
    fixed = unwrap_terminal_wrap(text)
    if fixed == text:
        return False
    set_clipboard_text(fixed.replace("\n", "\r\n"))
    return True


def trim_png(raw: bytes | None) -> bytes | None:
    if not raw or len(raw) < 32 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    end = raw.rfind(b"IEND")
    if end < 8:
        return None
    stop = end + 8
    if stop > len(raw) or stop > 8_000_000:
        return None
    return raw[:stop]


def dib_to_bmp(dib: bytes) -> bytes | None:
    if len(dib) < 40:
        return None
    header_size = int.from_bytes(dib[0:4], "little")
    if header_size < 40 or header_size > min(len(dib), 256):
        return None
    bit_count = int.from_bytes(dib[14:16], "little")
    compression = int.from_bytes(dib[16:20], "little")
    clr_used = int.from_bytes(dib[32:36], "little") if len(dib) >= 36 else 0
    extra = 12 if compression == 3 and header_size == 40 else 0
    colors = clr_used
    if colors == 0 and 0 < bit_count <= 8:
        colors = 1 << bit_count
    if bit_count == 0 or bit_count > 32:
        return None
    pixel_off = header_size + extra + colors * 4
    if pixel_off <= 0 or pixel_off > len(dib):
        return None
    file_off = 14 + pixel_off
    file_size = 14 + len(dib)
    return struct.pack("<2sIHHI", b"BM", file_size, 0, 0, file_off) + dib


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", wintypes.BOOL),
        ("SuppressExternalCodecs", wintypes.BOOL),
    ]


_GDIP_TOKEN = ctypes.c_ulong(0)
_ENCODERS: dict[str, _Guid] = {}


def _gdiplus():
    library = ctypes.windll.gdiplus
    library.GdiplusStartup.argtypes = [ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p, ctypes.c_void_p]
    library.GdiplusStartup.restype = ctypes.c_int
    library.GdipGetImageEncodersSize.argtypes = [ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
    library.GdipGetImageEncodersSize.restype = ctypes.c_int
    library.GdipGetImageEncoders.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    library.GdipGetImageEncoders.restype = ctypes.c_int
    library.GdipLoadImageFromFile.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
    library.GdipLoadImageFromFile.restype = ctypes.c_int
    library.GdipSaveImageToFile.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(_Guid), ctypes.c_void_p]
    library.GdipSaveImageToFile.restype = ctypes.c_int
    library.GdipDisposeImage.argtypes = [ctypes.c_void_p]
    library.GdipDisposeImage.restype = ctypes.c_int
    return library


def _ensure_gdiplus() -> bool:
    if _GDIP_TOKEN.value:
        return True
    startup = _GdiplusStartupInput(1, None, False, False)
    status = _gdiplus().GdiplusStartup(ctypes.byref(_GDIP_TOKEN), ctypes.byref(startup), None)
    return status == 0 and bool(_GDIP_TOKEN.value)


def _encoder(mime: str) -> _Guid | None:
    found = _ENCODERS.get(mime)
    if found is not None:
        return found
    if not _ensure_gdiplus():
        return None
    count = ctypes.c_uint()
    size = ctypes.c_uint()
    library = _gdiplus()
    if library.GdipGetImageEncodersSize(ctypes.byref(count), ctypes.byref(size)) != 0 or not size.value:
        return None
    buffer = ctypes.create_string_buffer(size.value)
    if library.GdipGetImageEncoders(count.value, size.value, buffer) != 0:
        return None
    pointer = ctypes.sizeof(ctypes.c_void_p)
    step = 32 + pointer * 5 + 16 + pointer * 2
    for index in range(count.value):
        base = index * step
        mime_at = base + 32 + 4 * pointer
        mime_ptr = int.from_bytes(buffer.raw[mime_at : mime_at + pointer], "little")
        if mime_ptr and ctypes.wstring_at(mime_ptr).lower() == mime:
            guid = _Guid.from_buffer_copy(buffer.raw[base : base + 16])
            _ENCODERS[mime] = guid
            return guid
    return None


def _convert_image(source: bytes, source_suffix: str, mime: str) -> bytes | None:
    if not source or not _encoder(mime):
        return None
    folder = paths()["data"] / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    src = folder / f"{stamp}{source_suffix}"
    dest = folder / f"{stamp}.out"
    image = ctypes.c_void_p()
    try:
        src.write_bytes(source)
        library = _gdiplus()
        if library.GdipLoadImageFromFile(str(src), ctypes.byref(image)) != 0 or not image.value:
            return None
        encoder = _encoder(mime)
        if encoder is None or library.GdipSaveImageToFile(image, str(dest), ctypes.byref(encoder), None) != 0:
            return None
        if not dest.is_file():
            return None
        return dest.read_bytes()
    except OSError:
        return None
    finally:
        if image.value:
            _gdiplus().GdipDisposeImage(image)
        src.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)


def dib_to_png(dib: bytes) -> bytes | None:
    bmp = dib_to_bmp(dib)
    if not bmp:
        return None
    converted = _convert_image(bmp, ".bmp", "image/png")
    return trim_png(converted)


def png_to_dib(png: bytes) -> bytes | None:
    picture = trim_png(png)
    if not picture:
        return None
    bmp = _convert_image(picture, ".png", "image/bmp")
    if not bmp or not bmp.startswith(b"BM") or len(bmp) < 54:
        return None
    return bmp[14:]


def saved_image(clip_id: int) -> Path | None:
    path = paths()["data"] / "images" / f"{clip_id}.png"
    if not path.is_file() and paths()["db"].exists():
        conn = connect()
        try:
            init_db(conn)
            image = conn.execute("SELECT png FROM clip_images WHERE clip_id=?", (clip_id,)).fetchone()
            if image:
                path.parent.mkdir(parents=True,exist_ok=True)
                temporary = path.with_suffix(".png.tmp")
                temporary.write_bytes(image[0])
                temporary.replace(path)
        finally:
            conn.close()
    try:
        if not path.is_file() or path.stat().st_size < 32:
            return None
        with path.open("rb") as handle:
            handle.seek(-24, os.SEEK_END)
            if b"IEND" not in handle.read():
                return None
    except OSError:
        return None
    return path


def own_paste_pending() -> bool:
    try:
        expected = paths()["suppress"].read_text(encoding="ascii").strip()
        return expected.isdigit() and int(expected) == user32.GetClipboardSequenceNumber()
    except OSError:
        return False


def mark_own_paste() -> None:
    clip_store.atomic_text(paths()["suppress"],str(user32.GetClipboardSequenceNumber())+"\n")


def history_panel_open() -> bool:
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    if user32.GetAsyncKeyState(0x5B) & 0x8000 or user32.GetAsyncKeyState(0x5C) & 0x8000:
        return True
    hwnd = int(user32.GetForegroundWindow() or 0)
    if not hwnd or window_class(hwnd) != "Windows.UI.Core.CoreWindow":
        return False
    _app, title = window_source(hwnd)
    return "Input Experience" in title or title == "Clipboard"


def read_global_text(handle: int) -> str | None:
    size = int(kernel32.GlobalSize(handle))
    if size < 2:
        return None
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        raw = ctypes.string_at(pointer,min(size,(MAX_READ+1)*4))
        return raw.decode("utf-16-le",errors="replace").split("\x00",1)[0]
    finally:
        kernel32.GlobalUnlock(handle)


def read_global_bytes(handle: int) -> bytes | None:
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        size = kernel32.GlobalSize(handle)
        if not size or size > 32_000_000:
            return None
        return ctypes.string_at(pointer, size)
    finally:
        kernel32.GlobalUnlock(handle)


def html_format_to_text(raw: bytes) -> str:
    decoded = raw.decode("utf-8", errors="replace")
    match = re.search(r"<!--StartFragment-->(.*)<!--EndFragment-->", decoded, re.S)
    chunk = match.group(1) if match else decoded
    chunk = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", chunk)
    chunk = re.sub(r"(?s)<[^>]+>", " ", chunk)
    chunk = html.unescape(chunk)
    return re.sub(r"\s+", " ", chunk).strip()


def read_clipboard() -> dict | None:
    if not user32.OpenClipboard(None):
        return None
    try:
        owner = int(user32.GetClipboardOwner() or 0)
        owner_app, owner_title = window_source(owner)
        if sensitive_source(owner_app,owner_title):
            return {"excluded": "protected-source"}
        for name in ("ExcludeClipboardContentFromMonitorProcessing","CanIncludeInClipboardHistory"):
            format_id = user32.RegisterClipboardFormatW(name)
            if format_id and user32.IsClipboardFormatAvailable(format_id):
                if name.startswith("Exclude"):
                    return {"excluded": "protected-format"}
                handle = user32.GetClipboardData(format_id)
                marker = read_global_bytes(handle) if handle else None
                if marker and len(marker)>=4 and struct.unpack("<I",marker[:4])[0] == 0:
                    return {"excluded": "protected-format"}
        text = None
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if handle:
                text = read_global_text(handle)
        if not (text and text.strip()):
            html_format = user32.RegisterClipboardFormatW("HTML Format")
            if html_format and user32.IsClipboardFormatAvailable(html_format):
                handle = user32.GetClipboardData(html_format)
                if handle:
                    raw = read_global_bytes(handle)
                    if raw:
                        text = html_format_to_text(raw)
        files: list[str] = []
        if user32.IsClipboardFormatAvailable(CF_HDROP):
            handle = user32.GetClipboardData(CF_HDROP)
            if handle:
                count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
                buffer = ctypes.create_unicode_buffer(32768)
                for index in range(min(int(count), 100)):
                    shell32.DragQueryFileW(handle, index, buffer, 32768)
                    if buffer.value:
                        files.append(buffer.value)
        has_image = bool(
            user32.IsClipboardFormatAvailable(CF_DIB) or user32.IsClipboardFormatAvailable(CF_DIBV5)
        )
        html_bytes = None
        html_format = user32.RegisterClipboardFormatW("HTML Format")
        if html_format and user32.IsClipboardFormatAvailable(html_format):
            handle = user32.GetClipboardData(html_format)
            if handle:
                raw_html = read_global_bytes(handle)
                if raw_html and len(raw_html) <= 120_000:
                    html_bytes = raw_html.split(b"\x00", 1)[0]
        png_bytes = None
        png_format = user32.RegisterClipboardFormatW("PNG")
        if png_format and user32.IsClipboardFormatAvailable(png_format):
            handle = user32.GetClipboardData(png_format)
            if handle:
                raw_png = read_global_bytes(handle)
                if raw_png and len(raw_png) <= 8_000_000:
                    png_bytes = raw_png
        dib = None
        if trim_png(png_bytes) is None:
            for image_format in (CF_DIBV5, CF_DIB):
                if not user32.IsClipboardFormatAvailable(image_format):
                    continue
                handle = user32.GetClipboardData(image_format)
                raw_dib = read_global_bytes(handle) if handle else None
                if raw_dib and 40 <= len(raw_dib) <= 24_000_000:
                    dib = raw_dib
                    break
        owner = user32.GetClipboardOwner()
        app, title = window_source(int(owner) if owner else 0)
        return {
            "sequence": user32.GetClipboardSequenceNumber(),
            "text": text,
            "files": files,
            "has_image": has_image or bool(png_bytes) or bool(dib),
            "app": app,
            "title": title,
            "html": html_bytes,
            "png": png_bytes,
            "dib": dib,
        }
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str, html_bytes: bytes | None = None, expected_sequence: int | None = None) -> bool:
    encoded = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not handle:
        raise OSError("clipboard alloc failed")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise OSError("clipboard lock failed")
    ctypes.memmove(pointer, encoded, len(encoded))
    kernel32.GlobalUnlock(handle)
    opened = False
    for _ in range(6):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        kernel32.GlobalFree(handle)
        raise OSError("clipboard open failed")
    try:
        if expected_sequence is not None and user32.GetClipboardSequenceNumber() != expected_sequence:
            return False
        if not user32.EmptyClipboard():
            raise OSError("clipboard empty failed")
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise OSError("clipboard set failed")
        handle = None
        html_handle = None
        if html_bytes:
            html_format = user32.RegisterClipboardFormatW("HTML Format")
            payload = html_bytes if html_bytes.endswith(b"\x00") else html_bytes + b"\x00"
            html_handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
            if html_handle:
                html_pointer = kernel32.GlobalLock(html_handle)
                if html_pointer:
                    ctypes.memmove(html_pointer, payload, len(payload))
                    kernel32.GlobalUnlock(html_handle)
                    if user32.SetClipboardData(html_format, html_handle):
                        html_handle = None
        if html_handle:
            kernel32.GlobalFree(html_handle)
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)
    return True


def set_clipboard_image(png: bytes) -> None:
    picture = trim_png(png)
    if not picture:
        raise OSError("picture is not a png")
    dib = png_to_dib(picture)
    png_format = user32.RegisterClipboardFormatW("PNG")
    if not png_format:
        raise OSError("png format unavailable")

    def alloc(payload: bytes) -> int | None:
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return None
        ctypes.memmove(pointer, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        return int(handle)

    png_handle = alloc(picture)
    dib_handle = alloc(dib) if dib else None
    if not png_handle:
        if dib_handle:
            kernel32.GlobalFree(dib_handle)
        raise OSError("clipboard alloc failed")
    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(png_handle)
        if dib_handle:
            kernel32.GlobalFree(dib_handle)
        raise OSError("clipboard open failed")
    try:
        if not user32.EmptyClipboard():
            raise OSError("clipboard empty failed")
        if not user32.SetClipboardData(png_format, png_handle):
            raise OSError("clipboard set failed")
        png_handle = None
        if dib_handle and user32.SetClipboardData(CF_DIB, dib_handle):
            dib_handle = None
    finally:
        user32.CloseClipboard()
        if png_handle:
            kernel32.GlobalFree(png_handle)
        if dib_handle:
            kernel32.GlobalFree(dib_handle)


def capture_once(fallback_app: str = "", fallback_title: str = "") -> dict | None:
    if own_paste_pending():
        return {"skipped": True}
    if sensitive_source(fallback_app,fallback_title):
        return {"skipped": True,"excluded":"protected-source"}
    snapshot = read_clipboard()
    if snapshot is None:
        return None
    if snapshot.get("excluded"):
        return {"skipped":True,"excluded":snapshot["excluded"]}
    app,title = choose_app(snapshot["app"],snapshot["title"],fallback_app,fallback_title)
    original = snapshot["text"]
    png_bytes = trim_png(snapshot.get("png"))
    if png_bytes is None and snapshot.get("dib"):
        png_bytes = dib_to_png(snapshot["dib"])
    # Store the eligible original before applying the accepted terminal-wrap repair.
    result = ingest(original,app=app,title=title,files=snapshot["files"],
                    has_image=snapshot["has_image"] or bool(png_bytes),
                    html_bytes=snapshot.get("html"),png_bytes=png_bytes)
    if result and original and terminal_host(app) and not snapshot["files"] and not png_bytes:
        fixed = unwrap_terminal_wrap(original)
        if fixed != original:
            try:
                if set_clipboard_text(fixed.replace("\n","\r\n"),expected_sequence=snapshot.get("sequence")):
                    mark_own_paste()
            except OSError:
                log("terminal repair deferred")
    if result and not result.get("duplicate") and "id" in result:
        PANEL["last_capture_at"] = clip_store.now()
        PANEL["last_error"] = None
    return result


def watcher_running() -> bool:
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def acquire_mutex() -> bool:
    global _MUTEX
    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    if not handle or already:
        if handle:
            kernel32.CloseHandle(handle)
        return False
    _MUTEX = handle
    return True


def health_snapshot() -> dict:
    location = paths()
    info = {"version":clip_store.VERSION,"collector_running":watcher_running(),"retention":"keep",
            "cloud_processing":False,"last_error":PANEL.get("last_error"),"database":str(location["db"])}
    if location["db"].exists():
        conn = sqlite3.connect(location["db"].as_uri()+"?mode=ro",uri=True)
        try:
            info["records"],info["last_capture_at"] = conn.execute("SELECT count(*),max(last_seen_at) FROM clips").fetchone()
            if conn.execute("PRAGMA user_version").fetchone()[0]>=2:
                info["pending_exports"] = conn.execute("SELECT count(*) FROM clip_jobs WHERE status='pending'").fetchone()[0]
                info["occurrences"] = conn.execute("SELECT count(*) FROM clip_occurrences").fetchone()[0]
        finally:
            conn.close()
    info["last_backup"] = None
    backup_note = location["data"] / "last-backup.json"
    if backup_note.is_file():
        try:
            info["last_backup"] = json.loads(backup_note.read_text(encoding="utf-8"))
        except (OSError,ValueError):
            pass
    info["known_capture_gaps"] = PANEL.get("capture_gaps",0)
    return info


def watch() -> int:
    if not acquire_mutex():
        emit("Clipboard collector is already running.")
        return 0
    paths()["stop"].unlink(missing_ok=True)
    log(f"started version={clip_store.VERSION} pid={os.getpid()}")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    conn = connect()
    try:
        init_db(conn)
    finally:
        conn.close()
    PANEL["last_error"] = None
    PANEL["capture_gaps"] = 0
    hot_hwnd = install_hotkey()
    start_panel_server()
    last_housekeeping = 0.0
    last_export = 0.0
    last_event = time.monotonic()
    last_sequence = user32.GetClipboardSequenceNumber()
    try:
        capture_once()
        while not paths()["stop"].exists():
            pump_hotkey(hot_hwnd)
            pending = PANEL.get("pending_clip")
            if pending and time.monotonic() >= pending["due"]:
                if user32.GetClipboardSequenceNumber() != pending["sequence"]:
                    PANEL["capture_gaps"] += 1
                    PANEL["last_error"] = "clipboard-changed-before-retry"
                    PANEL["pending_clip"] = None
                else:
                    try:
                        result = capture_once(pending["app"],pending["title"])
                    except (OSError,sqlite3.Error,ValueError):
                        result = None
                    if result is None and pending["tries"] < 8:
                        pending["tries"] += 1
                        pending["due"] = time.monotonic()+0.05
                    else:
                        PANEL["pending_clip"] = None
                        if result is None:
                            PANEL["last_error"] = "clipboard-unreadable"
                            PANEL["capture_gaps"] += 1
            # Fallback if Windows refused listener registration; do not leave capture disabled.
            if not PANEL.get("listen"):
                sequence = user32.GetClipboardSequenceNumber()
                if sequence != last_sequence:
                    last_sequence = sequence
                    capture_once()
            if PANEL.get("last_event"):
                last_event = PANEL["last_event"]
            if time.monotonic()-last_event > 0.25 and time.monotonic()-last_export > 1:
                process_pending(limit=8)
                last_export = time.monotonic()
            if time.monotonic()-last_housekeeping > 10:
                clip_store.atomic_text(paths()["data"]/"heartbeat.json",
                    json.dumps({"pid":os.getpid(),"observed_at":clip_store.now(),**health_snapshot()}))
                last_housekeeping = time.monotonic()
            time.sleep(0.01 if PANEL.get("listen") else 0.05)
    except Exception:
        PANEL["last_error"] = "collector-stopped-unexpectedly"
        log("collector stopped unexpectedly")
        raise
    finally:
        paths()["stop"].unlink(missing_ok=True)
        if PANEL.get("server"):
            PANEL["server"].shutdown()
            PANEL["server"].server_close()
        log("stopped")
    return 0


def fetch(conn: sqlite3.Connection, clip_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()


def search_rows(conn: sqlite3.Connection, query: str, kind: str | None, limit: int) -> list[sqlite3.Row]:
    return clip_store.query_rows(conn, query, kind, limit)


def format_row(row: sqlite3.Row) -> str:
    preview = re.sub(r"\s+", " ", row["preview"] or "")
    if len(preview) > 88:
        preview = preview[:85] + "..."
    app = (row["source_app"] or "-")[:22]
    return f"{row['id']:>6}  {fmt_time(row['captured_at'])}  {row['kind']:<8}  {app:<22}  {preview}"


def print_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        emit("No copies matched.")
        return
    for row in rows:
        emit(format_row(row))


def recent(kind: str | None, limit: int) -> int:
    conn = connect()
    try:
        init_db(conn)
        if kind:
            rows = list(
                conn.execute(
                    "SELECT * FROM clips WHERE kind = ? ORDER BY id DESC LIMIT ?",
                    (kind, limit),
                )
            )
        else:
            rows = list(conn.execute("SELECT * FROM clips ORDER BY id DESC LIMIT ?", (limit,)))
    finally:
        conn.close()
    if not rows:
        if kind:
            emit(f"No {kind} copies yet.")
        else:
            state = "running" if watcher_running() else "stopped"
            emit(f"Nothing copied yet. Collector is {state}.")
        return 0
    print_rows(rows)
    return 0


def show(clip_id: int) -> int:
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn, clip_id)
    finally:
        conn.close()
    if row is None:
        emit(f"No copy #{clip_id}.")
        return 1
    emit(f"id: {row['id']}")
    emit(f"when: {fmt_time(row['captured_at'])}")
    emit(f"kind: {row['kind']}")
    emit(f"app: {row['source_app'] or '-'}")
    emit(f"title: {row['source_title'] or '-'}")
    emit(f"chars: {row['char_len']}")
    emit(f"copies: {row['hit_count']}")
    if row["sidecar"]:
        emit(f"file: {row['sidecar']}")
    if row["pinned"]:
        emit("pinned: yes")
    emit("")
    if row["body"]:
        emit(row["body"])
    else:
        emit("The value was not stored.")
    return 0


def set_pin(clip_id: int, pinned: int) -> int:
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn, clip_id)
        if row is None:
            emit(f"No copy #{clip_id}.")
            return 1
        conn.execute("UPDATE clips SET pinned = ? WHERE id = ?", (pinned, clip_id))
        conn.commit()
    finally:
        conn.close()
    emit(f"{'Pinned' if pinned else 'Unpinned'} #{clip_id}.")
    return 0


def copy_back(clip_id: int) -> int:
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn, clip_id)
    finally:
        conn.close()
    if row is None:
        emit(f"No copy #{clip_id}.")
        return 1
    picture = saved_image(clip_id)
    if picture is None and not row["body"]:
        emit("That copy has nothing stored to paste.")
        return 1
    try:
        if picture is not None and not row["body"]:
            set_clipboard_image(picture.read_bytes())
        else:
            html_bytes = None
            try:
                extra = json.loads(row["extra_json"] or "{}")
                encoded = extra.get("html_b64")
                if encoded:
                    html_bytes = __import__("base64").b64decode(encoded)
            except (json.JSONDecodeError, ValueError):
                html_bytes = None
            set_clipboard_text(row["body"], html_bytes)
    except OSError:
        paths()["suppress"].unlink(missing_ok=True)
        emit("Clipboard is busy.")
        return 1
    mark_own_paste()
    emit(f"Copied #{clip_id} back to the clipboard.")
    return 0


def open_clip(clip_id: int) -> int:
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn, clip_id)
    finally:
        conn.close()
    if row is None:
        emit(f"No copy #{clip_id}.")
        return 1
    if row["sidecar"] and Path(row["sidecar"]).is_file():
        target = row["sidecar"]
    elif row["body"]:
        folder = paths()["data"] / "views"
        folder.mkdir(parents=True, exist_ok=True)
        target = str(folder / f"{clip_id}.md")
        Path(target).write_text(row["body"], encoding="utf-8")
    else:
        emit("That copy has no stored text.")
        return 1
    subprocess.Popen(["notepad.exe", target])
    emit(target)
    return 0


def status() -> int:
    running = watcher_running()
    location = paths()
    emit(f"collector: {'running' if running else 'stopped'}")
    emit(f"database: {location['db']}")
    emit(f"prompts: {location['prompts']}")
    emit(f"snippets: {location['snippets']}")
    emit(f"fabric: {fabric_root()}")
    if not location["db"].exists():
        emit("clips: 0")
        return 0
    conn = connect()
    try:
        init_db(conn)
        total = conn.execute("SELECT COUNT(*) AS n FROM clips").fetchone()["n"]
        prompts = conn.execute("SELECT COUNT(*) AS n FROM clips WHERE kind = 'prompt'").fetchone()["n"]
        code = conn.execute("SELECT COUNT(*) AS n FROM clips WHERE kind = 'code'").fetchone()["n"]
        secrets = conn.execute("SELECT COUNT(*) AS n FROM clips WHERE kind = 'secret'").fetchone()["n"]
        last = conn.execute("SELECT * FROM clips ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    emit(f"clips: {total}")
    emit(f"saved prompts: {prompts}")
    emit(f"saved code: {code}")
    emit(f"secrets logged without the value: {secrets}")
    if last:
        emit("last: " + format_row(last))
    return 0


def stop() -> int:
    flag = paths()["stop"]
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("stop\n", encoding="ascii")
    for _ in range(20):
        if not watcher_running():
            emit("Clipboard collector stopped.")
            return 0
        time.sleep(0.2)
    emit("Stop requested. The collector is still shutting down.")
    return 1


def fabric_root() -> Path:
    return Path(os.environ["PROMPT_FABRIC"]) if os.environ.get("PROMPT_FABRIC") else starlight_dir("prompt-fabric")


def entry_title(body: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", body)[:8]
    if not words:
        return "Untitled capture"
    return " ".join(words)[:72]


def find_fabric_entry(clip_id: int) -> Path | None:
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn,clip_id)
        if row is None:
            return None
        recorded = conn.execute("SELECT path FROM clip_promotions WHERE clip_uid=? LIMIT 1",(row["uid"],)).fetchone()
        if recorded and Path(recorded[0]).is_file():
            return Path(recorded[0])
    finally:
        conn.close()
    books = fabric_root() / "books"
    if not books.exists():
        return None
    uid_needle = f"clip_uid: {quote_yaml(row['uid'])}\n"
    legacy_id = f"clip_id: {clip_id}\n"
    date_needle = f"captured_at: {quote_yaml(row['captured_at'])}\n"
    for path in books.glob("*/entries/*.md"):
        if path.is_symlink():
            continue
        with path.open(encoding="utf-8") as handle:
            head = handle.read(2000)
        if uid_needle in head or ("clip_uid:" not in head and legacy_id in head and date_needle in head):
            return path
    return None


def promote(clip_id: int, scope: str) -> int:
    book = FABRIC_BOOKS.get(scope)
    if book is None:
        emit("Scope must be frank, starlight, arcanea, frankx, or general.")
        return 2
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn, clip_id)
    finally:
        conn.close()
    if row is None:
        emit(f"No copy #{clip_id}.")
        return 1
    if not row["body"]:
        emit("That copy has no stored text to curate.")
        return 1
    existing = find_fabric_entry(clip_id)
    if existing:
        record_promotion(row, scope, existing)
        emit(str(existing))
        return 0
    root = fabric_root()
    folder = root / "books" / book
    entries = folder / "entries"
    entries.mkdir(parents=True, exist_ok=True)
    number = len(list(entries.glob("*.md"))) + 1
    body = row["body"].replace("\r\n", "\n").strip("\n")
    title = entry_title(body)
    fence = "````" if "```" in body else "```"
    captured = row["captured_at"]
    day = fmt_time(captured)[:10]
    entry = entries / f"{number:04d}-clip-{row['uid'][:12]}.md"
    text = "\n".join(
        [
            "---",
            f"entry: {number:04d}",
            f"clip_id: {clip_id}",
            f"clip_uid: {quote_yaml(row['uid'])}",
            f"use_case: {quote_yaml(row['use_case'])}",
            f"scope: {scope}",
            f"book: {book}",
            "status: captured",
            "publish: no",
            "second_brain: hold",
            "public_library: hold",
            f"source_app: {quote_yaml(row['source_app'] or '')}",
            f"sidecar: {quote_yaml(row['sidecar'] or '')}",
            f"captured_at: {quote_yaml(captured)}",
            "---",
            "",
            f"### {number:04d} - {title}",
            "",
            f"Date: {day}",
            "Status: captured",
            "Pattern link: private until a red-team pass",
            "",
            "#### Raw Capture",
            "",
            fence + "text",
            body,
            fence,
            "",
            "#### Original Prompt",
            "",
            fence + "text",
            body.strip(),
            fence,
            "",
            "#### Optimized Prompt",
            "",
            fence + "text",
            "Awaiting the curator pass. Keep the intent. Give the prompt an identity, ordered steps, an output contract, and an input slot. Leave it private.",
            fence,
            "",
            "#### Optimization Notes",
            "",
            "- Specificity:",
            "- Success criterion:",
            "- Examples:",
            "- Structure:",
            "- Contradiction audit:",
            "- Output contract:",
            "- Safety boundary:",
            "- Predicted delta:",
            "",
            "#### Failure Modes",
            "",
            "- The voice gets broader than the task.",
            "- Context the raw prompt assumed is missing.",
            "- The output has no contract.",
            "- Private wording is copied into the public prompt library.",
            "",
            "#### Eval Notes",
            "",
            "Run the optimized prompt on one real task. Keep it only if the result is more decisive and more usable than the raw capture.",
            "",
            "#### Advance",
            "",
            "After three uses, distill the reusable move. File one second-brain atom only when Frank asks. Publish to frankxai/prompt-library only after attribution and a red-team pass.",
            "",
        ]
    )
    entry.write_text(text, encoding="utf-8")
    book_page = folder / "prompt-book.md"
    if not book_page.exists():
        book_page.write_text(
            "\n".join(
                [
                    f"# {book}",
                    "",
                    "Status: private",
                    "Owner: Frank",
                    f"Scope: {scope}",
                    f"Created: {day}",
                    f"Updated: {day}",
                    "",
                    "Clipboard captures promoted with `clips promote` land in `entries/`.",
                    "The public prompt library stays the reviewed corpus. This book is the living layer.",
                    "",
                    "## Entries",
                    "",
                    f"- [{number:04d} - {title}](entries/{entry.name})",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    else:
        with book_page.open("a", encoding="utf-8") as handle:
            handle.write(f"- [{number:04d} - {title}](entries/{entry.name})\n")
    index = root / "INDEX.md"
    line = f"| {number:04d} | {scope} | {title} | captured | {clip_id} | {entry} |"
    if not index.exists():
        index.write_text(
            "\n".join(
                [
                    "# Prompt fabric",
                    "",
                    "Private captures. `clips promote <id> --scope frank|starlight|arcanea|frankx|general` adds a row.",
                    "",
                    "| entry | scope | title | status | clip | file |",
                    "| --- | --- | --- | --- | --- | --- |",
                    line,
                    "",
                ]
            ),
            encoding="utf-8",
        )
    else:
        with index.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    record_promotion(row, scope, entry)
    emit(str(entry))
    return 0


def record_promotion(row, scope: str, entry: Path) -> None:
    conn = connect()
    try:
        init_db(conn)
        conn.execute("UPDATE clips SET state='saved',pinned=1 WHERE id=?", (row["id"],))
        conn.execute("INSERT OR REPLACE INTO clip_promotions VALUES(?,?,?,?)",
                     (row["uid"],scope,str(entry),clip_store.now()))
        conn.commit()
    finally:
        conn.close()


def vault_atoms() -> Path:
    override = os.environ.get("STARLIGHT_VAULT")
    if override:
        return clip_store.safe_vault(Path(override)) / "atoms"
    candidate = Path(r"C:\Users\frank\starlight\repos\starlight-memory-vault")
    if candidate.is_dir():
        return candidate / "atoms"
    return paths()["root"] / "memory-atoms"


def remember_one(clip_id: int) -> int:
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn, clip_id)
    finally:
        conn.close()
    if row is None:
        emit(f"No copy #{clip_id}.")
        return 1
    if row["kind"] == "secret" or not row["body"]:
        emit("That copy stays out of the second brain.")
        return 1
    atoms = vault_atoms()
    atoms.mkdir(parents=True, exist_ok=True)
    needle = f"clipboard_uid: {quote_yaml(row['uid'])}\n"
    for path in atoms.glob("clipboard-*.md"):
        try:
            head = path.read_text(encoding="utf-8")[:1200]
        except OSError:
            continue
        if needle in head:
            emit(str(path))
            return 0
    body = row["body"].replace("\r\n", "\n").strip()
    if len(body) > 12000:
        body = body[:12000].rstrip() + "\n\n[truncated]"
    title = entry_title(body)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "copy"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:6]
    memory_id = f"clipboard-{row['uid'][:12]}-{slug}-{digest}"
    reason = ""
    try:
        extra = json.loads(row["extra_json"] or "{}")
        reason = str(extra.get("reason") or "")
    except json.JSONDecodeError:
        reason = ""
    kind = row["kind"] or "text"
    app = display_app(row["source_app"] or "")
    lines = [
        "---",
        f"memory_id: {memory_id}",
        f"summary: {quote_yaml(title)}",
        "memory_type: episodic",
        "vault: technical",
        f"tags: [clipboard, {kind}]",
        "importance: 0.4",
        "confidence: 0.7",
        "trust: 0.6",
        "privacy_class: private",
        "retention_policy: review",
        "tenant_id: frank",
        f"observed_at: {quote_yaml(row['captured_at'] or utc_now())}",
        f"clipboard_clip: {clip_id}",
        f"clipboard_uid: {quote_yaml(row['uid'])}",
        "index_state: pending",
        "---",
        "",
        title,
        "",
        f"Filed from the Starlight clipboard ({app or 'unknown app'}, {kind}). One copy, because it was asked for.",
        "",
    ]
    if reason:
        lines.extend([reason, ""])
    lines.extend([body, ""])
    path = atoms / f"{memory_id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    existing = find_fabric_entry(clip_id)
    if existing and existing.is_file():
        text = existing.read_text(encoding="utf-8")
        if "second_brain: hold" in text:
            existing.write_text(text.replace("second_brain: hold", "second_brain: filed", 1), encoding="utf-8")
    emit(str(path))
    return 0


def show_fabric() -> int:
    index = fabric_root() / "INDEX.md"
    if not index.exists():
        emit("No prompt fabric entries yet. Promote one with clips promote <id> --scope frank.")
        return 0
    emit(index.read_text(encoding="utf-8").rstrip())
    return 0


def open_folder() -> int:
    folder = paths()["prompts"]
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["explorer.exe", str(folder)])
    emit(str(folder))
    return 0


def self_test() -> int:
    import tempfile

    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    fake_key = _j("s", "k-") + ("ab" * 16)
    phrase = _j("sum", "mer", "fish")
    assignment = _j("pass", "word") + "=" + phrase
    redacted, labels = redact("prefix " + fake_key + " suffix")
    check("redact-provider", fake_key not in redacted and "openai" in labels)
    prompt = "You are a librarian.\nReturn only the word kelpbridge.\n" + assignment + "\n"
    cleaned, prompt_labels = redact(prompt)
    check("partial-keeps-word", "kelpbridge" in cleaned and phrase not in cleaned)
    check("partial-label", "assignment" in prompt_labels)
    check("classify-prompt", classify_text(cleaned) == "prompt")
    check("classify-url", classify_text("https://frankx.ai/library") == "url")
    check("classify-command", classify_text("git status --porcelain=v1") == "command")
    check("classify-code", classify_text("def hello():\n    return 1\n") == "code")
    check("clean-title-normal", clean_title("chrome.exe", "GitHub - Google Chrome") == "GitHub")
    check("clean-title-edge", clean_title("msedge.exe", "Stack Overflow - Microsoft Edge") == "Stack Overflow")
    check("clean-title-vscode", clean_title("code.exe", "clip.py - Visual Studio Code") == "clip.py")
    check("clean-title-whitespace", clean_title("notepad.exe", "  My   Note  - Notepad") == "My Note")
    check("clean-title-empty", clean_title("chrome.exe", None) == "")
    check("clean-title-app-name-match", clean_title("chrome.exe", "Chrome") == "")
    check("clean-title-exact-app-match", clean_title("Code.exe", "code.exe") == "")
    check("clean-title-truncate", len(clean_title("app.exe", "A" * 100)) == 72)
    check("sensitive-app", sensitive_source("Bitwarden.exe", "Vault") is True)
    pem_kind = _j("RSA ", "PRI", "VATE KEY")
    pem = ("-" * 5) + "BEGIN " + pem_kind + ("-" * 5) + "\nline\n" + ("-" * 5) + "END " + pem_kind + ("-" * 5)
    pem_clean, pem_labels = redact(pem)
    check("redact-pem", "line" not in pem_clean and "private-key" in pem_labels)
    def wrap_words(source: str, width: int) -> str:
        lines: list[str] = []
        current = ""
        for word in source.split():
            trial = word if not current else current + " " + word
            if len(trial) <= width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return "\n".join(lines)

    sentence = (
        "The agent printed this sentence across the width of the terminal window "
        "and the copy kept every painted break in the paragraph so the next line "
        "was still part of that same thought before the paragraph ended."
    )
    sample = wrap_words(sentence, 78)
    rejoined = unwrap_terminal_wrap(sample)
    check("unwrap-joins-edge", rejoined.rstrip("\n") == sentence and "\n" not in rejoined.rstrip("\n"))
    check("unwrap-once", unwrap_terminal_wrap(rejoined) == rejoined)
    paragraph = sample + "\n\nNext paragraph stays on its own line and should not be glued on."
    split = unwrap_terminal_wrap(paragraph)
    check("unwrap-keeps-paragraph", split.startswith(sentence + "\n\nNext paragraph"))
    code = "def build(value):\n    return {'value': value, 'ok': True}\n\nprint(build(1))\n"
    check("unwrap-keeps-code", unwrap_terminal_wrap(code) == code)
    short = "one\ntwo\nthree\nfour\n"
    check("unwrap-keeps-short", unwrap_terminal_wrap(short) == short)
    check("terminal-host", terminal_host("WindowsTerminal.exe") and not terminal_host("chrome.exe"))

    previous = os.environ.get("CLIP_HOME")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CLIP_HOME"] = tmp
            secret = ingest(fake_key, app="notepad.exe", title="note")
            check("secret-recorded", bool(secret) and secret["kind"] == "secret")
            saved = ingest(prompt, app="Cursor.exe", title="prompt.md")
            check("prompt-kind", bool(saved) and saved["kind"] == "prompt")
            process_pending()
            conn = connect()
            try:
                init_db(conn)
                row = fetch(conn, int(secret["id"]))
                check("secret-body-empty", row is not None and row["body"] is None)
                check("secret-preview", row is not None and fake_key not in (row["preview"] or ""))
                found = search_rows(conn, "kelpbridge", "prompt", 5)
                check("search-prompt", any(item["id"] == saved["id"] for item in found))
                shown = fetch(conn, int(saved["id"]))
                check("sidecar", bool(shown and shown["sidecar"] and Path(shown["sidecar"]).is_file()))
                check("device", shown is not None and shown["device"] == this_device())
                body = Path(shown["sidecar"]).read_text(encoding="utf-8") if shown and shown["sidecar"] else ""
                check("sidecar-redacted", phrase not in body and "kelpbridge" in body)
            finally:
                conn.close()
            again = ingest(cleaned, app="Cursor.exe", title="prompt.md")
            check("duplicate", bool(again) and again.get("duplicate") is True)
            os.environ["PROMPT_FABRIC"] = str(Path(tmp) / "fabric")
            check("promote", promote(int(saved["id"]), "starlight") == 0)
            promoted = next((Path(tmp) / "fabric" / "books").glob("*/entries/*.md"))
            promoted_text = promoted.read_text(encoding="utf-8")
            check("promote-raw", "kelpbridge" in promoted_text and phrase not in promoted_text)
            check("promote-once", promote(int(saved["id"]), "starlight") == 0)
            check("ignore-owner", choose_app("svchost.exe", "Clipboard", "chrome.exe", "GitHub") == ("chrome.exe", "GitHub"))
            check("display-chrome", display_app("chrome.exe") == "Chrome")
            sample_png = bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
            )
            check("trim-png", trim_png(sample_png + b"\x00\x00") == sample_png)
            pixel = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 32, 0, 16, 0, 0, 0, 0) + (b"\x10\x20\xf0\xff" * 4)
            converted = dib_to_png(pixel)
            check("dib-png", bool(converted) and trim_png(converted) == converted)
            if converted:
                shot = ingest(None, has_image=True, png_bytes=converted, app="SnippingTool.exe", title="Snip")
                shot_path = saved_image(int(shot["id"])) if shot else None
                check("image-file", shot_path is not None)
                again = ingest(None, has_image=True, png_bytes=converted, app="SnippingTool.exe", title="Snip")
                check("image-duplicate", bool(again) and again.get("duplicate") is True)
            os.environ["STARLIGHT_VAULT"] = str(Path(tmp) / "vault")
            check("remember", remember_one(int(saved["id"])) == 0)
            check("remember-once", remember_one(int(saved["id"])) == 0)
            atoms = list((Path(tmp) / "vault" / "atoms").glob("clipboard-*.md"))
            atom_text = atoms[0].read_text(encoding="utf-8") if len(atoms) == 1 else ""
            check("one-atom", len(atoms) == 1 and "kelpbridge" in atom_text and phrase not in atom_text)
            check("remember-secret", remember_one(int(secret["id"])) == 1)
            url = ingest("https://frankx.ai/library", app="chrome.exe", title="FrankX")
            check("url-kind", bool(url) and url["kind"] == "url")
            manager = ingest("vault sample phrase", app="Bitwarden.exe", title="Bitwarden")
            conn = connect()
            try:
                hidden = fetch(conn, int(manager["id"])) if manager else None
                check(
                    "manager-hidden",
                    hidden is not None and hidden["body"] is None and "vault sample" not in (hidden["preview"] or ""),
                )
            finally:
                conn.close()
    finally:
        if previous is None:
            os.environ.pop("CLIP_HOME", None)
        else:
            os.environ["CLIP_HOME"] = previous
        os.environ.pop("PROMPT_FABRIC", None)
        os.environ.pop("STARLIGHT_VAULT", None)

    if failures:
        emit("SELF-TEST FAILED")
        for name in failures:
            emit(f"- {name}")
        return 1
    emit("SELF-TEST PASS")
    return 0


BOARD_TITLE = "Starlight Clipboard"


def load_board_rows(query: str) -> list[sqlite3.Row]:
    conn = connect()
    try:
        init_db(conn)
        return search_rows(conn,query,None,100)
    finally:
        conn.close()


def focus_window(hwnd: int) -> None:
    if not hwnd:
        return
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_ulonglong]
    user32.keybd_event.restype = None
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 0x0002, 0)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.ShowWindow(hwnd, 9)
    pid = wintypes.DWORD()
    their_thread = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    our_thread = kernel32.GetCurrentThreadId()
    if their_thread and our_thread:
        user32.AttachThreadInput(our_thread, their_thread, True)
    user32.SetForegroundWindow(hwnd)
    if their_thread and our_thread:
        user32.AttachThreadInput(our_thread, their_thread, False)


def paste_keys() -> None:
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_ulonglong]
    user32.keybd_event.restype = None
    key_up = 0x0002
    user32.keybd_event(0x11, 0, 0, 0)
    user32.keybd_event(0x56, 0, 0, 0)
    user32.keybd_event(0x56, 0, key_up, 0)
    user32.keybd_event(0x11, 0, key_up, 0)


def find_board_window() -> int:
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    found = user32.FindWindowW(None, BOARD_TITLE)
    return int(found or 0)


def window_class(hwnd: int) -> str:
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, name, 256)
    return name.value


def edge_path() -> Path | None:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def board_items(query: str) -> dict:
    rows = load_board_rows(query)
    devices = []
    items = []
    for row in rows:
        device = row["device"] or this_device()
        if device not in devices:
            devices.append(device)
        body = row["body"] or ""
        preview = row["preview"] or ""
        if not query.strip() and len(re.findall(r"[A-Za-z0-9]", preview)) < 2:
            continue
        items.append(
            {
                "id": int(row["id"]),
                "kind": row["kind"],
                "preview": preview,
                "body": body[:400],
                "more": len(body) > 400,
                "state": row["state"],
                "use_case": row["use_case"],
                "copies": int(row["hit_count"]),
                "captured_at": row["captured_at"],
                "app": display_app(row["source_app"] or ""),
                "title": clean_title(row["source_app"] or "", row["source_title"] or ""),
                "device": device,
                "pinned": int(row["pinned"] or 0),
                "book": row["state"] == "saved",
                "stored": bool(body),
                "reason": "",
                "image": False,
            }
        )
        picture = saved_image(int(row["id"]))
        items[-1]["image"] = picture is not None
        if picture is not None:
            items[-1]["stored"] = True
        try:
            extra = json.loads(row["extra_json"] or "{}")
            items[-1]["reason"] = str(extra.get("reason") or "")
            items[-1]["incomplete"] = bool(extra.get("truncated"))
        except json.JSONDecodeError:
            pass
    return {"device": this_device(), "devices": devices, "items": items}


PANEL = {"hwnd": 0, "token": "", "port": 0, "target": 0, "server": None, "hotkey": 0}


def panel_file() -> Path:
    return paths()["data"] / "panel.json"


def remember_target(hwnd: int | None = None) -> int:
    current = int(hwnd or user32.GetForegroundWindow() or 0)
    if current and current == int(PANEL["hwnd"] or 0):
        return int(PANEL["target"] or 0)
    if current:
        PANEL["target"] = current
    return int(PANEL["target"] or 0)


def palette_bounds() -> tuple[int, int, int, int]:
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    width, height = 960, 620
    screen_w = user32.GetSystemMetrics(0) or 1280
    screen_h = user32.GetSystemMetrics(1) or 800
    return max(0, (screen_w - width) // 2), max(0, int(screen_h * 0.14)), width, height


def strip_palette_chrome(hwnd: int) -> None:
    getter = getattr(user32, "GetWindowLongPtrW", None)
    setter = getattr(user32, "SetWindowLongPtrW", None)
    if getter is None or setter is None:
        return
    getter.argtypes = [wintypes.HWND, ctypes.c_int]
    getter.restype = ctypes.c_ssize_t
    setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    setter.restype = ctypes.c_ssize_t
    style = getter(hwnd, -16) or 0
    style &= ~(0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000)
    style |= 0x80000000 | 0x10000000
    setter(hwnd, -16, style)


def tint_palette(hwnd: int) -> None:
    try:
        dwmapi = ctypes.windll.dwmapi
        color = ctypes.c_int(0x000F1111)
        text = ctypes.c_int(0x00E6F0F4)
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)
        dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), 4)
        dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(color), 4)
    except Exception:
        return


def place_palette(hwnd: int, show: bool) -> None:
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    if not hwnd or not user32.IsWindow(hwnd):
        return
    tint_palette(hwnd)
    x, y, width, height = palette_bounds()
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    flags = 0x0020 | (0x0040 if show else 0x0080)
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), x, y, width, height, flags)
    PANEL["hwnd"] = int(hwnd)


def hide_palette() -> None:
    hwnd = int(PANEL["hwnd"] or 0)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    if hwnd:
        user32.ShowWindow(hwnd, 0)


def delete_clip(clip_id: int) -> bool:
    conn = connect()
    try:
        init_db(conn)
        row = fetch(conn, clip_id)
        if row is None:
            return False
        sidecar = row["sidecar"]
        conn.execute("DELETE FROM clips_fts WHERE rowid = ?", (clip_id,))
        conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
        conn.commit()
    finally:
        conn.close()
    if sidecar and not find_fabric_entry(clip_id):
        path = Path(sidecar)
        if path.is_file():
            path.unlink()
    image = paths()["data"] / "images" / f"{clip_id}.png"
    if image.is_file():
        image.unlink()
    return True


def start_panel_server() -> None:
    if PANEL["server"] is not None:
        return
    token = secrets.token_urlsafe(18)
    PANEL["token"] = token

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args) -> None:
            return

        def _allowed(self) -> bool:
            sent = (parse_qs(urlparse(self.path).query).get("k") or [""])[0]
            bearer = self.headers.get("Authorization","")
            if bearer.startswith("Bearer "):
                sent = bearer[7:]
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{PANEL['port']}"
            if origin and origin != expected:
                return False
            if self.headers.get("Host") != f"127.0.0.1:{PANEL['port']}":
                return False
            return bool(PANEL["token"]) and secrets.compare_digest(sent, PANEL["token"])

        def _send(self, code: int, payload: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 512_000:
                raise ValueError("Request size is outside the allowed range.")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value,dict):
                raise ValueError("Expected a JSON object.")
            return value

        def do_GET(self) -> None:
            if not self._allowed():
                self.send_error(404)
                return
            path = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            if path in ("/", "/index.html"):
                page = Path(__file__).with_name("board.html").read_text(encoding="utf-8")
                self._send(200, page.replace("__TOKEN__", PANEL["token"]).encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/image":
                try:
                    clip_id = int((query.get("id") or ["0"])[0])
                except ValueError:
                    self.send_error(404)
                    return
                image = saved_image(clip_id)
                if image is None:
                    self.send_error(404)
                    return
                payload = image.read_bytes()
                self._send(200, payload, "image/png")
                return
            if path == "/api/health":
                self._json(200,health_snapshot())
                return
            if path == "/api/detail":
                try:
                    clip_id = int((query.get("id") or ["0"])[0])
                    conn = connect()
                    try:
                        init_db(conn)
                        row = fetch(conn,clip_id)
                        detail = {"id":clip_id,"body":row["body"] or "","state":row["state"]} if row else None
                    finally:
                        conn.close()
                    self._json(200 if detail else 404,detail or {"error":"Copy not found."})
                except ValueError:
                    self._json(400,{"error":"Invalid copy ID."})
                return
            if path == "/api/items":
                try:
                    self._json(200,board_items((query.get("q") or [""])[0]))
                except ValueError as error:
                    self._json(400,{"error":str(error)})
                return
            if path == "/api/raise":
                target = int((query.get("target") or ["0"])[0] or 0)
                show_palette(target or None)
                self._json(200, {"ok": True})
                return
            if path == "/api/hide":
                hide_palette()
                self._json(200, {"ok": True})
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if not self._allowed():
                self.send_error(404)
                return
            path = urlparse(self.path).path
            try:
                payload = self._body()
                if path == "/api/backup":
                    folder = clip_store.backup(paths()["root"])
                    self._json(200,{"ok":True,"snapshot":folder.name})
                    return
                if path == "/api/add":
                    text = payload.get("text")
                    if not isinstance(text,str) or not text.strip() or len(text)>100_000:
                        raise ValueError("Write an idea of up to 100,000 characters.")
                    result = ingest(text,app="starlight-clipboard",title="Saved idea")
                    if result and result.get("kind") != "secret":
                        set_state(result["id"],"saved")
                    self._json(200,{"ok":bool(result),"id":result.get("id") if result else None})
                    return
                clip_id = int(payload.get("id"))
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                self._json(400,{"ok":False,"error":str(error) or "Invalid request."})
                return
            except (OSError,sqlite3.Error):
                self._json(503,{"ok":False,"error":"Local storage is unavailable. Retry after checking disk space."})
                return
            if path == "/api/state":
                state = str(payload.get("state",""))
                if state not in clip_store.STATES:
                    self._json(400,{"ok":False,"error":"Unknown library state."})
                else:
                    self._json(200,{"ok":set_state(clip_id,state) == 0})
                return
            if path == "/api/paste":
                if copy_back(clip_id) != 0:
                    self._json(400, {"ok": False})
                    return
                target = int(PANEL["target"] or 0)
                hide_palette()
                self._json(200, {"ok": True})

                def finish() -> None:
                    time.sleep(0.08)
                    if target:
                        focus_window(target)
                        time.sleep(0.05)
                        paste_keys()

                threading.Thread(target=finish, daemon=True).start()
                return
            if path == "/api/copy":
                self._json(200, {"ok": copy_back(clip_id) == 0})
                return
            if path == "/api/pin":
                self._json(200, {"ok": set_pin(clip_id, int(payload.get("pinned") or 0)) == 0})
                return
            if path == "/api/book":
                scope = "frank" if str(payload.get("kind") or "") == "prompt" else str(payload.get("scope") or "starlight")
                self._json(200, {"ok": promote(clip_id, scope) == 0})
                return
            if path == "/api/brain":
                self._json(200, {"ok": remember_one(clip_id) == 0})
                return
            if path == "/api/delete":
                self._json(200, {"ok": set_state(clip_id,"archived") == 0})
                return
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    PANEL["server"] = server
    PANEL["port"] = int(server.server_address[1])
    paths()["data"].mkdir(parents=True, exist_ok=True)
    panel_file().write_text(
        json.dumps({"port": PANEL["port"], "token": PANEL["token"]}),
        encoding="utf-8",
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()


def launch_palette_window() -> int:
    browser = edge_path()
    if browser is None or not PANEL["port"]:
        return 0
    x, y, width, height = palette_bounds()
    url = f"http://127.0.0.1:{PANEL['port']}/?k={PANEL['token']}"
    # This is the user's utility window, isolated from signed-in browser sessions.
    profile = paths()["root"] / "ui-profile"
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(browser),
            f"--user-data-dir={profile}",
            f"--app={url}",
            f"--window-size={width},{height}",
            f"--window-position={x},{y}",
            "--new-window",
            "--no-first-run",
            "--disable-extensions",
            "--disable-sync",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 8
    while time.time() < deadline:
        hwnd = find_board_window()
        if hwnd and window_class(hwnd) != "TkTopLevel":
            return hwnd
        time.sleep(0.05)
    return 0


def show_palette(target: int | None = None) -> None:
    if target:
        remember_target(int(target))
    else:
        remember_target()
    start_panel_server()
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    hwnd = int(PANEL["hwnd"] or 0)
    if not hwnd or not user32.IsWindow(hwnd):
        hwnd = launch_palette_window()
    if not hwnd:
        log("palette window did not open")
        return
    place_palette(hwnd, True)
    focus_window(hwnd)


def install_hotkey() -> int:
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    hwnd = user32.CreateWindowExW(0, "Static", "StarlightClipHotkey", 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
    if not hwnd:
        log("hotkey window failed")
        return 0
    if not user32.RegisterHotKey(hwnd, 1, 0x0001 | 0x0002 | 0x4000, 0x56):
        log(f"hotkey unavailable ({kernel32.GetLastError()})")
    user32.AddClipboardFormatListener.argtypes = [wintypes.HWND]
    user32.AddClipboardFormatListener.restype = wintypes.BOOL
    PANEL["listen"] = bool(user32.AddClipboardFormatListener(hwnd))
    PANEL["hotkey"] = int(hwnd)
    log("hotkey ready")
    log("clipboard listener ready" if PANEL["listen"] else "clipboard listener unavailable")
    return int(hwnd)


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class Msg(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", Point),
    ]


# ctypes never frees struct/pointer types, so these must be created once, not per 20 ms poll.
user32.PeekMessageW.argtypes = [ctypes.POINTER(Msg), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(Msg)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(Msg)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t


def pump_hotkey(hwnd: int) -> None:
    if not hwnd:
        return
    message = Msg()
    while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
        if message.message == 0x031D:
            sequence = user32.GetClipboardSequenceNumber()
            if sequence == PANEL.get("last_sequence"):
                continue
            PANEL["last_sequence"] = sequence
            PANEL["last_event"] = time.monotonic()
            if own_paste_pending():
                continue
            foreground = int(user32.GetForegroundWindow() or 0)
            fallback_app,fallback_title = window_source(foreground) if foreground else ("","")
            old = PANEL.get("pending_clip")
            if old and old["sequence"] != sequence:
                PANEL["capture_gaps"] = PANEL.get("capture_gaps",0)+1
            try:
                result = capture_once(fallback_app,fallback_title)
            except (OSError,sqlite3.Error,ValueError):
                result = None
                PANEL["last_error"] = "capture-failed"
            PANEL["pending_clip"] = None if result is not None else {
                "due":time.monotonic()+0.03,"app":fallback_app,"title":fallback_title,
                "tries":0,"sequence":sequence}
            continue
        if message.message == 0x0312:
            target = int(user32.GetForegroundWindow() or 0)
            if target and target != int(PANEL["hwnd"] or 0):
                PANEL["target"] = target
            try:
                show_palette(int(PANEL["target"] or 0))
            except Exception:
                log("palette open failed")
        else:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))


def board() -> int:
    target = int(user32.GetForegroundWindow() or 0)
    state = panel_file()
    if state.is_file() and watcher_running():
        try:
            saved = json.loads(state.read_text(encoding="utf-8"))
            url = f"http://127.0.0.1:{int(saved['port'])}/api/raise?k={saved['token']}&target={target}"
            import urllib.request

            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return 0
        except Exception:
            log("palette raise failed")
    if watcher_running():
        emit("Clipboard collector is running, but the palette did not open.")
        return 1
    emit("Clipboard collector is stopped. Run clips watch or the installed start shortcut.")
    return 1

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clips",
        description="Search everything copied on this PC. Prompts and longer code are saved as files.",
    )
    sub = parser.add_subparsers(dest="cmd")

    recent_cmd = sub.add_parser("recent", help="Show the newest copies")
    recent_cmd.add_argument("--limit", type=int, default=20)
    recent_cmd.add_argument("--kind", default=None)

    search = sub.add_parser("search", help="Full-text search")
    search.add_argument("query", nargs="+")
    search.add_argument("--kind", default=None)
    search.add_argument("--limit", type=int, default=30)

    prompts = sub.add_parser("prompts", help="List saved prompts")
    prompts.add_argument("--limit", type=int, default=30)

    snippets = sub.add_parser("snippets", help="List saved code")
    snippets.add_argument("--limit", type=int, default=30)

    for name in ("show", "pin", "unpin", "copy", "open"):
        command = sub.add_parser(name)
        command.add_argument("id", type=int)

    promote_cmd = sub.add_parser("promote", help="File a copy into the private prompt fabric")
    promote_cmd.add_argument("id", type=int)
    promote_cmd.add_argument("--scope", default="frank")

    remember_cmd = sub.add_parser("remember", help="File one copy in the second brain")
    remember_cmd.add_argument("id", type=int)

    sub.add_parser("fabric", help="List curated prompt-fabric entries")
    sub.add_parser("board", help="Open the clipboard window")
    status_cmd = sub.add_parser("status")
    status_cmd.add_argument("--json",action="store_true")
    doctor = sub.add_parser("doctor",help="Read collector, database, export and backup health")
    doctor.add_argument("--json",action="store_true")
    backup_cmd = sub.add_parser("backup",help="Create a consistent private local snapshot")
    backup_cmd.add_argument("--destination",type=Path)
    restore_cmd = sub.add_parser("restore",help="Verify and restore a snapshot into a new directory")
    restore_cmd.add_argument("snapshot",type=Path)
    restore_cmd.add_argument("--target",type=Path,required=True)
    export_cmd = sub.add_parser("export",help="Export a bounded query to a new private JSONL file")
    export_cmd.add_argument("--query",default="state:any")
    export_cmd.add_argument("--destination",type=Path,required=True)
    for name in ("archive","unarchive","resolve"):
        state_cmd = sub.add_parser(name)
        state_cmd.add_argument("id",type=int)
    add_cmd = sub.add_parser("add",help="Save an idea explicitly")
    add_cmd.add_argument("text",nargs="+")
    sub.add_parser("reindex",help="Refresh local prompt metadata and repair pending exports")
    sub.add_parser("watch", help="Run the collector in this window")
    sub.add_parser("stop")
    sub.add_parser("folder", help="Open the saved prompts folder")
    sub.add_parser("self-test")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.cmd
    if command in (None, "recent"):
        return recent(getattr(args, "kind", None), getattr(args, "limit", 20))
    if command == "search":
        conn = connect()
        try:
            init_db(conn)
            rows = search_rows(conn, " ".join(args.query), args.kind, args.limit)
        finally:
            conn.close()
        print_rows(rows)
        return 0 if rows else 1
    if command == "prompts":
        return recent("prompt", args.limit)
    if command == "snippets":
        return recent("code", args.limit)
    if command == "show":
        return show(args.id)
    if command == "pin":
        return set_pin(args.id, 1)
    if command == "unpin":
        return set_pin(args.id, 0)
    if command == "copy":
        return copy_back(args.id)
    if command == "open":
        return open_clip(args.id)
    if command == "promote":
        return promote(args.id, args.scope)
    if command == "remember":
        return remember_one(args.id)
    if command == "fabric":
        return show_fabric()
    if command == "board":
        return board()
    if command in {"status","doctor"}:
        info = health_snapshot()
        if args.json:
            emit(json.dumps(info,ensure_ascii=False))
        else:
            for key,value in info.items():
                emit(f"{key}: {value}")
        return 0
    if command == "backup":
        emit(str(clip_store.backup(paths()["root"],args.destination)))
        return 0
    if command == "restore":
        emit(str(clip_store.restore(args.snapshot,args.target)))
        return 0
    if command == "export":
        conn = connect()
        try:
            init_db(conn)
            count = clip_store.export_jsonl(conn,args.destination,args.query)
        finally:
            conn.close()
        emit(f"Exported {count} private records.")
        return 0
    if command in {"archive","unarchive","resolve"}:
        return set_state(args.id,{"archive":"archived","unarchive":"active","resolve":"resolved"}[command])
    if command == "add":
        result = ingest(" ".join(args.text),app="starlight-clipboard",title="Saved idea")
        if result and result["kind"] != "secret":
            set_state(result["id"],"saved")
        emit(f"Saved #{result['id']}." if result else "Nothing to save.")
        return 0 if result else 1
    if command == "reindex":
        emit(f"Reindexed {reindex_library()} records.")
        while process_pending(100):
            pass
        return 0
    if command == "watch":
        return watch()
    if command == "stop":
        return stop()
    if command == "folder":
        return open_folder()
    if command == "self-test":
        return self_test()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
