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
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(r"C:\Users\frank\.starlight\clipboard-index")
DEFAULT_FABRIC = Path(r"C:\Users\frank\.starlight\prompt-fabric")
FABRIC_BOOKS = {
    "frank": "frank-operating-voice",
    "starlight": "starlight-operations",
    "arcanea": "arcanea-studio",
    "frankx": "frankx-commercial",
    "general": "general",
}
MUTEX_NAME = "Local\\StarlightClipboardIndex"
MAX_READ = 1_000_000
MAX_CHARS = 200_000
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
    root = Path(os.environ["CLIP_HOME"]) if os.environ.get("CLIP_HOME") else DEFAULT_ROOT
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
    conn.execute("PRAGMA synchronous=NORMAL")
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
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


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


def ingest(
    text: str | None,
    *,
    app: str = "",
    title: str = "",
    files: list[str] | None = None,
    has_image: bool = False,
    device: str | None = None,
    html_bytes: bytes | None = None,
) -> dict | None:
    files = files or []
    raw = (text or "").replace("\x00", "")
    read_truncated = False
    if len(raw) > MAX_READ:
        raw = raw[:MAX_READ]
        read_truncated = True
    if not raw.strip() and not files and not has_image:
        return None

    labels: list[str] = []
    secret_only = False
    truncated = read_truncated
    kind = "text"
    body: str | None
    stored_for_hash: str | None
    if sensitive_source(app, title) and raw.strip():
        secret_only = True
        kind = "secret"
        body = None
        labels = ["vault-app"]
        stored_for_hash = None
    elif raw.strip():
        redacted, labels = redact(raw)
        if labels and only_redactions(redacted):
            secret_only = True
            kind = "secret"
            body = None
            stored_for_hash = None
        else:
            kind = classify_text(redacted)
            if len(redacted) > MAX_CHARS:
                body = redacted[:MAX_CHARS]
                truncated = True
            else:
                body = redacted
            stored_for_hash = redacted
    elif files:
        kind = "files"
        shown = files[:100]
        body = "\n".join(shown)
        stored_for_hash = body
        truncated = truncated or len(files) > 100
    else:
        kind = "image"
        body = None
        stored_for_hash = None

    if secret_only or kind == "image":
        digest = hashlib.sha256(f"{kind}|{time.time_ns()}".encode("utf-8")).hexdigest()
    else:
        digest = hashlib.sha256((stored_for_hash or "").encode("utf-8")).hexdigest()

    if kind == "secret":
        preview = "[redacted:" + ",".join(labels or ["secret"]) + "]"
        char_len = 0
    elif kind == "image":
        preview = "[image]"
        char_len = 0
    else:
        preview = preview_of(body or "")
        char_len = len(stored_for_hash or "")

    extra: dict = {}
    if labels:
        extra["redactions"] = labels
    if truncated:
        extra["truncated"] = True
    if has_image and kind != "image":
        extra["image"] = True
    if files and kind != "files":
        extra["files"] = files[:20]
    reason = prompt_reason(body or "") if kind == "prompt" and body else None
    if reason:
        extra["reason"] = reason
    if html_bytes and kind not in {"secret", "image"} and len(html_bytes) <= 120_000:
        extra["html_b64"] = __import__("base64").b64encode(html_bytes).decode("ascii")

    captured_at = utc_now()
    device_name = clip_device(app, device)
    conn = connect()
    try:
        init_db(conn)
        suppress = paths()["suppress"]
        if suppress.exists():
            expected = suppress.read_text(encoding="ascii").strip()
            if expected and expected == digest:
                suppress.unlink(missing_ok=True)
                return None
        last = conn.execute(
            "SELECT id, sha256, hit_count FROM clips ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last and last["sha256"] == digest:
            conn.execute(
                "UPDATE clips SET hit_count = ?, last_seen_at = ? WHERE id = ?",
                (int(last["hit_count"]) + 1, captured_at, int(last["id"])),
            )
            conn.commit()
            return {"id": int(last["id"]), "duplicate": True, "kind": kind}

        cursor = conn.execute(
            """
            INSERT INTO clips (
              captured_at, last_seen_at, kind, source_app, source_title, sha256,
              char_len, preview, body, extra_json, device
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                captured_at,
                captured_at,
                kind,
                app[:80],
                title[:200],
                digest,
                char_len,
                preview,
                body,
                json.dumps(extra, ensure_ascii=False) if extra else None,
                device_name,
            ),
        )
        clip_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO clips_fts(rowid, preview, body, source_app, source_title, kind)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (clip_id, preview, body or "", app[:80], title[:200], kind),
        )
        sidecar = None
        if body and kind == "prompt":
            sidecar = write_sidecar(kind, clip_id, captured_at, app, title, body, labels)
        elif body and kind == "code" and char_len >= 80:
            sidecar = write_sidecar(kind, clip_id, captured_at, app, title, body, labels)
        if sidecar:
            conn.execute("UPDATE clips SET sidecar = ? WHERE id = ?", (sidecar, clip_id))
        conn.commit()
        try:
            if device_name == this_device() or device_name == "Phone":
                export_device()
        except Exception:
            log("device export failed")
        return {"id": clip_id, "duplicate": False, "kind": kind, "chars": char_len}
    finally:
        conn.close()


def prune(conn: sqlite3.Connection) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - KEEP_DAYS * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doomed = [
        int(row["id"])
        for row in conn.execute(
            "SELECT id FROM clips WHERE pinned = 0 AND captured_at < ?",
            (cutoff_iso,),
        )
    ]
    overflow = int(conn.execute("SELECT COUNT(*) AS n FROM clips WHERE pinned = 0").fetchone()["n"])
    if overflow > MAX_ROWS:
        doomed.extend(
            int(row["id"])
            for row in conn.execute(
                "SELECT id FROM clips WHERE pinned = 0 ORDER BY id ASC LIMIT ?",
                (overflow - MAX_ROWS,),
            )
        )
    doomed = sorted(set(doomed))
    if not doomed:
        return 0
    slots = ",".join("?" for _ in doomed)
    sidecars = [
        row["sidecar"]
        for row in conn.execute(
            f"SELECT sidecar FROM clips WHERE id IN ({slots}) AND sidecar IS NOT NULL",
            doomed,
        )
    ]
    conn.execute(f"DELETE FROM clips_fts WHERE rowid IN ({slots})", doomed)
    conn.execute(f"DELETE FROM clips WHERE id IN ({slots})", doomed)
    conn.commit()
    for sidecar in sidecars:
        if not sidecar:
            continue
        still = conn.execute("SELECT 1 FROM clips WHERE sidecar = ? LIMIT 1", (sidecar,)).fetchone()
        if still:
            continue
        path = Path(sidecar)
        if path.is_file():
            path.unlink()
    return len(doomed)


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


def read_global_text(handle: int) -> str | None:
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        return ctypes.wstring_at(pointer)
    finally:
        kernel32.GlobalUnlock(handle)


def read_global_bytes(handle: int) -> bytes | None:
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        size = kernel32.GlobalSize(handle)
        if not size:
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
    opened = False
    for _ in range(6):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        return None
    try:
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
        owner = user32.GetClipboardOwner()
        app, title = window_source(int(owner) if owner else 0)
        return {"text": text, "files": files, "has_image": has_image, "app": app, "title": title, "html": html_bytes}
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str, html_bytes: bytes | None = None) -> None:
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


def capture_once(fallback_app: str = "", fallback_title: str = "") -> dict | None:
    snapshot = read_clipboard()
    if snapshot is None:
        log("capture skipped: clipboard busy")
        return None
    app = snapshot["app"] or fallback_app
    title = snapshot["title"] or fallback_title
    if app.lower() in {"python.exe", "pythonw.exe"}:
        app, title = fallback_app, fallback_title
    result = ingest(
        snapshot["text"],
        app=app,
        title=title,
        files=snapshot["files"],
        has_image=snapshot["has_image"],
        html_bytes=snapshot.get("html"),
    )
    if result and not result.get("duplicate"):
        log(
            f"recorded id={result['id']} kind={result['kind']} chars={result.get('chars', 0)} app={snapshot['app']}"
        )
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


def watch() -> int:
    if not acquire_mutex():
        if sys.stdout is not None:
            emit("Clipboard collector is already running.")
        return 0
    stop = paths()["stop"]
    stop.unlink(missing_ok=True)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    log(f"started pid={os.getpid()}")
    try:
        export_device()
    except Exception:
        log("device export failed")
    try:
        capture_once()
    except Exception:
        log("initial capture failed")
    sequence = user32.GetClipboardSequenceNumber()
    last_prune = time.monotonic()
    last_peers = 0.0
    last_clip = time.monotonic()
    hot_hwnd = install_hotkey()
    start_panel_server()
    while True:
        pump_hotkey(hot_hwnd)
        if stop.exists():
            stop.unlink(missing_ok=True)
            log("stopped")
            return 0
        if PANEL.get("listen"):
            time.sleep(0.02)
            if time.monotonic() - last_peers > 20:
                try:
                    import_peers()
                except Exception:
                    log("peer import failed")
                last_peers = time.monotonic()
            if time.monotonic() - last_prune > 3600:
                try:
                    conn = connect()
                    try:
                        init_db(conn)
                        removed = prune(conn)
                        if removed:
                            log(f"pruned {removed}")
                    finally:
                        conn.close()
                except Exception:
                    log("prune failed")
                last_prune = time.monotonic()
            continue
        if time.monotonic() - last_clip < POLL_SECONDS:
            time.sleep(0.02)
            continue
        last_clip = time.monotonic()
        current = user32.GetClipboardSequenceNumber()
        if current != sequence:
            sequence = current
            try:
                capture_once()
            except Exception:
                log("capture failed")
        if time.monotonic() - last_peers > 20:
            try:
                import_peers()
            except Exception:
                log("peer import failed")
            last_peers = time.monotonic()
        if time.monotonic() - last_prune > 3600:
            try:
                conn = connect()
                try:
                    init_db(conn)
                    removed = prune(conn)
                    if removed:
                        log(f"pruned {removed}")
                finally:
                    conn.close()
            except Exception:
                log("prune failed")
            last_prune = time.monotonic()


def fetch(conn: sqlite3.Connection, clip_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()


def search_rows(conn: sqlite3.Connection, query: str, kind: str | None, limit: int) -> list[sqlite3.Row]:
    tokens = re.findall(r"[^\W_]{2,}", query, flags=re.UNICODE)[:12]
    kind_sql = " AND c.kind = ?" if kind else ""
    if tokens:
        match = " AND ".join(f'"{token}"*' for token in tokens)
        args: list = [match]
        if kind:
            args.append(kind)
        args.append(limit)
        try:
            return list(
                conn.execute(
                    f"""
                    SELECT c.* FROM clips_fts
                    JOIN clips c ON c.id = clips_fts.rowid
                    WHERE clips_fts MATCH ?{kind_sql}
                    ORDER BY c.id DESC
                    LIMIT ?
                    """,
                    args,
                )
            )
        except sqlite3.OperationalError:
            pass
    like = f"%{query.strip()}%"
    args = [like]
    if kind:
        args.append(kind)
    args.append(limit)
    return list(
        conn.execute(
            f"""
            SELECT * FROM clips c
            WHERE c.preview LIKE ?{kind_sql}
            ORDER BY c.id DESC
            LIMIT ?
            """,
            args,
        )
    )


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
    if not row["body"]:
        emit("That copy has no stored text.")
        return 1
    digest = hashlib.sha256(row["body"].encode("utf-8")).hexdigest()
    paths()["data"].mkdir(parents=True, exist_ok=True)
    paths()["suppress"].write_text(digest, encoding="ascii")
    html_bytes = None
    try:
        extra = json.loads(row["extra_json"] or "{}")
        encoded = extra.get("html_b64")
        if encoded:
            html_bytes = __import__("base64").b64decode(encoded)
    except (json.JSONDecodeError, ValueError):
        html_bytes = None
    try:
        set_clipboard_text(row["body"], html_bytes)
    except OSError:
        paths()["suppress"].unlink(missing_ok=True)
        emit("Clipboard is busy.")
        return 1
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
    return Path(os.environ["PROMPT_FABRIC"]) if os.environ.get("PROMPT_FABRIC") else DEFAULT_FABRIC


def entry_title(body: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", body)[:8]
    if not words:
        return "Untitled capture"
    return " ".join(words)[:72]


def find_fabric_entry(clip_id: int) -> Path | None:
    books = fabric_root() / "books"
    if not books.exists():
        return None
    needle = f"clip_id: {clip_id}\n"
    for path in books.glob("*/entries/*.md"):
        if needle in path.read_text(encoding="utf-8"):
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
    entry = entries / f"{number:04d}-clip-{clip_id}.md"
    text = "\n".join(
        [
            "---",
            f"entry: {number:04d}",
            f"clip_id: {clip_id}",
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
    emit(str(entry))
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
    check("sensitive-app", sensitive_source("Bitwarden.exe", "Vault") is True)
    pem_kind = _j("RSA ", "PRI", "VATE KEY")
    pem = ("-" * 5) + "BEGIN " + pem_kind + ("-" * 5) + "\nline\n" + ("-" * 5) + "END " + pem_kind + ("-" * 5)
    pem_clean, pem_labels = redact(pem)
    check("redact-pem", "line" not in pem_clean and "private-key" in pem_labels)

    previous = os.environ.get("CLIP_HOME")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CLIP_HOME"] = tmp
            secret = ingest(fake_key, app="notepad.exe", title="note")
            check("secret-recorded", bool(secret) and secret["kind"] == "secret")
            saved = ingest(prompt, app="Cursor.exe", title="prompt.md")
            check("prompt-kind", bool(saved) and saved["kind"] == "prompt")
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
        if query.strip():
            return search_rows(conn, query, None, 80)
        return list(
            conn.execute("SELECT * FROM clips ORDER BY pinned DESC, id DESC LIMIT 80")
        )
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
    import_peers()
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
                "body": body[:8000],
                "more": len(body) > 8000,
                "captured_at": row["captured_at"],
                "app": (row["source_app"] or "").removesuffix(".exe"),
                "device": device,
                "pinned": int(row["pinned"] or 0),
                "book": find_fabric_entry(int(row["id"])) is not None,
                "stored": bool(body),
                "reason": "",
            }
        )
        try:
            extra = json.loads(row["extra_json"] or "{}")
            items[-1]["reason"] = str(extra.get("reason") or "")
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
    width, height = 880, 560
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
            return bool(PANEL["token"]) and secrets.compare_digest(sent, PANEL["token"])

        def _send(self, code: int, payload: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

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
            if path == "/api/items":
                self._json(200, board_items((query.get("q") or [""])[0]))
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
                clip_id = int(payload.get("id"))
            except (TypeError, ValueError, json.JSONDecodeError):
                self._json(400, {"ok": False})
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
            if path == "/api/delete":
                self._json(200, {"ok": delete_clip(clip_id)})
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
    subprocess.Popen(
        [
            str(browser),
            f"--app={url}",
            f"--window-size={width},{height}",
            f"--window-position={x},{y}",
            "--new-window",
            "--no-first-run",
            "--disable-extensions",
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
        return int(hwnd)
    user32.AddClipboardFormatListener.argtypes = [wintypes.HWND]
    user32.AddClipboardFormatListener.restype = wintypes.BOOL
    PANEL["listen"] = bool(user32.AddClipboardFormatListener(hwnd))
    PANEL["hotkey"] = int(hwnd)
    log("hotkey ready")
    log("clipboard listener ready" if PANEL["listen"] else "clipboard listener unavailable")
    return int(hwnd)


def pump_hotkey(hwnd: int) -> None:
    if not hwnd:
        return

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

    user32.PeekMessageW.argtypes = [ctypes.POINTER(Msg), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(Msg)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(Msg)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    message = Msg()
    while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
        if message.message == 0x031D:
            foreground = int(user32.GetForegroundWindow() or 0)
            fallback_app, fallback_title = ("", "")
            if foreground and foreground != int(PANEL.get("hwnd") or 0):
                fallback_app, fallback_title = window_source(foreground)
            try:
                capture_once(fallback_app, fallback_title)
            except Exception:
                log("capture failed")
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
    emit("Clipboard collector is stopped. It starts again at login.")
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

    sub.add_parser("fabric", help="List curated prompt-fabric entries")
    sub.add_parser("board", help="Open the clipboard window")
    sub.add_parser("status")
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
    if command == "fabric":
        return show_fabric()
    if command == "board":
        return board()
    if command == "status":
        return status()
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
