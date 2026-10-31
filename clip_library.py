"""Private music collections, provenance-bearing labels and bounded portable handoffs."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid

import clip_store

SCHEMA = "starlight.clipboard-library.v1"
MAX_BUNDLE = 450_000
STARTERS = (
    ("midnight-piano", "Midnight piano", "Intimate piano directions to return to.", "use:suno piano"),
    ("cinematic-ascent", "Cinematic ascent", "Expansive scenes, strings and gradual builds.", "use:suno cinematic"),
    ("neon-motion", "Neon motion", "Electronic textures and forward movement.", "use:suno synth"),
    ("deep-focus", "Deep focus", "Ambient space and quiet concentration.", "use:suno ambient"),
)


def migrate(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS library_collections(
        id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,
        mode TEXT NOT NULL,query TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS library_members(
        collection_id TEXT NOT NULL REFERENCES library_collections(id),
        clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
        PRIMARY KEY(collection_id,clip_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS library_tags(
        clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
        label TEXT NOT NULL,source TEXT NOT NULL,reason TEXT NOT NULL,
        updated_at TEXT NOT NULL,PRIMARY KEY(clip_id,label))""")
    for key, name, description, query in STARTERS:
        conn.execute("INSERT OR IGNORE INTO library_collections VALUES(?,?,?,?,?,1,?)",
                     (key, name, description, "smart", query, clip_store.now()))


def text(value, maximum, field, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f"{field} is missing or too long.")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in value):
        raise ValueError(f"{field} contains unsupported control characters.")
    return value.strip()


def tag_name(value):
    return unicodedata.normalize("NFKC", text(value, 40, "Tag")).casefold()


def identity(value):
    original = value
    value = text(value, 160, "Identity")
    if value != original or not re.fullmatch(r"[A-Za-z0-9:_-]+", value):
        raise ValueError("Identity contains unsupported characters.")
    return value


def collection_value(payload):
    name = text(payload.get("name"), 80, "Collection name")
    description = text(payload.get("description", ""), 400, "Description", True)
    mode = payload.get("mode", "manual")
    query = text(payload.get("query", ""), 240, "Smart query", True)
    if not isinstance(mode, str) or mode not in {"manual", "smart"}:
        raise ValueError("Choose a manual or smart collection.")
    if mode == "smart":
        if not query:
            raise ValueError("A smart collection needs a search query.")
        _, filters = clip_store.parse_query(query)
        if "vibe" in filters:
            raise ValueError("A smart collection cannot refer to another collection.")
    else:
        query = ""
    return name, description, mode, query


def save_collection(conn, payload):
    values = collection_value(payload)
    key = identity(payload["id"]) if payload.get("id") else uuid.uuid4().hex
    prior = conn.execute("SELECT * FROM library_collections WHERE id=?", (key,)).fetchone()
    if values[2] == "smart":
        clip_store.query_rows(conn, values[3], limit=1)  # validate dates and FTS before writing
    with conn:
        if prior:
            if payload.get("version") != prior["version"]:
                raise ValueError("This collection changed. Reload it before saving; your draft is still available.")
            changed = conn.execute("UPDATE library_collections SET name=?,description=?,mode=?,query=?,version=version+1,updated_at=? WHERE id=? AND version=?",
                         (*values, clip_store.now(), key, payload["version"]))
            if changed.rowcount != 1:
                raise ValueError("This collection changed. Reload it before saving; your draft is still available.")
        else:
            if conn.execute("SELECT count(*) FROM library_collections").fetchone()[0] >= 100:
                raise ValueError("This library supports up to 100 collections.")
            conn.execute("INSERT INTO library_collections VALUES(?,?,?,?,?,1,?)", (key, *values, clip_store.now()))
    return key


def usable(conn, clip_id):
    row = conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    if row is None or row["kind"] in {"secret", "image", "files"} or not row["body"]:
        raise ValueError("Choose a retained text capture.")
    return row


def set_tags(conn, clip_id, labels, source="user", reason="Edited in the private library"):
    usable(conn, clip_id)
    if not isinstance(labels, list) or len(labels) > 20:
        raise ValueError("Use up to 20 tags.")
    labels = sorted({tag_name(label) for label in labels})
    if not isinstance(source, str) or source not in {"user", "agent", "local-rule"}:
        raise ValueError("Tag provenance must be user, agent or local-rule.")
    existing = {row[0] for row in conn.execute("SELECT label FROM library_tags WHERE clip_id=?", (clip_id,))}
    if len(set(labels) | (existing if source != "user" else set())) > 20:
        raise ValueError("A capture supports up to 20 tags. Review its existing labels first.")
    reason = text(reason, 240, "Tag explanation")
    with conn:
        if source == "user":
            conn.execute("DELETE FROM library_tags WHERE clip_id=?", (clip_id,))
        for label in labels:
            conn.execute("""INSERT INTO library_tags VALUES(?,?,?,?,?)
                ON CONFLICT(clip_id,label) DO UPDATE SET source=excluded.source,
                reason=excluded.reason,updated_at=excluded.updated_at WHERE library_tags.source!='user'""",
                         (clip_id, label, source, reason, clip_store.now()))
    return labels


def membership(conn, collection_id, clip_id, present):
    usable(conn, clip_id)
    row = conn.execute("SELECT mode FROM library_collections WHERE id=?", (identity(collection_id),)).fetchone()
    if row is None or row[0] != "manual":
        raise ValueError("Choose a manual collection; smart collections match their query.")
    with conn:
        if present:
            conn.execute("INSERT OR IGNORE INTO library_members VALUES(?,?)", (collection_id, clip_id))
        else:
            conn.execute("DELETE FROM library_members WHERE collection_id=? AND clip_id=?", (collection_id, clip_id))


def selected_ids(conn, key):
    row = conn.execute("SELECT * FROM library_collections WHERE id=?", (identity(key),)).fetchone()
    if row is None:
        raise ValueError("Collection not found.")
    if row["mode"] == "manual":
        return [x[0] for x in conn.execute("SELECT clip_id FROM library_members WHERE collection_id=?", (key,))]
    return [x["id"] for x in clip_store.query_rows(conn, row["query"], limit=1000)]


def snapshot(conn, clip_id=None):
    collections = []
    for row in conn.execute("SELECT * FROM library_collections ORDER BY lower(name),id"):
        entry = dict(row)
        if row["mode"] == "manual":
            count = conn.execute("SELECT count(*) FROM library_members WHERE collection_id=?", (row["id"],)).fetchone()[0]
            contains = bool(conn.execute("SELECT 1 FROM library_members WHERE collection_id=? AND clip_id=?", (row["id"],clip_id)).fetchone())
            entry.update(count=count, contains=contains, count_bounded=False)
        else:
            ids = selected_ids(conn, row["id"])
            entry.update(count=len(ids), contains=clip_id in ids if clip_id is not None else False,
                         count_bounded=len(ids) >= 1000)
        collections.append(entry)
    tags = [dict(row) for row in conn.execute("SELECT label,source,reason FROM library_tags WHERE clip_id=? ORDER BY label", (clip_id,))] if clip_id else []
    return {"collections": collections, "tags": tags, "sync": "local-only", "cloud_processing": False}


def suggestions(conn, clip_id):
    body = usable(conn, clip_id)["body"][:12000].casefold()
    existing = {r[0] for r in conn.execute("SELECT label FROM library_tags WHERE clip_id=?", (clip_id,))}
    vocabulary = {
        "cinematic": ("cinematic", "orchestral"), "piano": ("piano", "felt keys"),
        "ambient": ("ambient", "atmospheric"), "electronic": ("synth", "electronic"),
        "intimate": ("intimate", "gentle", "quiet"), "energetic": ("driving", "energetic", "festival"),
        "melancholic": ("melancholic", "wistful"), "instrumental": ("instrumental", "no vocals"),
        "vocals": ("singer", "vocalist"), "strings": ("strings", "violin", "cello"),
    }
    found = []
    for label, words in vocabulary.items():
        match = next((word for word in words if re.search(r"\b" + re.escape(word) + r"\b", body)), None)
        if match and label not in existing:
            found.append({"label": label, "source": "local-rule", "reason": f"Prompt wording includes '{match}'. Audio and submission are unverified."})
    return found


def export_bundle(conn, query="use:suno", collection_id=None):
    if collection_id:
        query = "state:any vibe:" + identity(collection_id)
    rows = clip_store.query_rows(conn, query, limit=1000)
    if len(rows) >= 1000:
        raise ValueError("Narrow the handoff to fewer than 1,000 captures.")
    records = []
    for row in rows:
        if row["kind"] in {"secret", "image", "files"} or not row["body"]:
            continue
        if len(row["body"]) > 100_000:
            raise ValueError("An original is too long for a portable handoff. Use the encrypted full-archive backup.")
        records.append({key: row[key] for key in ("uid", "body", "kind", "captured_at", "last_seen_at", "source_app", "source_title", "device", "use_case")})
    ids = {row["uid"] for row in records}
    collections = [dict(row) for row in conn.execute("SELECT id,name,description,mode,query FROM library_collections ORDER BY id") if not collection_id or row["id"] == collection_id]
    group_ids = {group["id"] for group in collections}
    members = [{"collection": row[0], "uid": row[1]} for row in conn.execute("SELECT m.collection_id,c.uid FROM library_members m JOIN clips c ON c.id=m.clip_id") if row[1] in ids and row[0] in group_ids]
    tags = [{"uid": row[0], "label": row[1], "source": row[2], "reason": row[3]} for row in conn.execute("SELECT c.uid,t.label,t.source,t.reason FROM library_tags t JOIN clips c ON c.id=t.clip_id") if row[0] in ids]
    packet = {"schema": SCHEMA, "created_at": clip_store.now(), "privacy": "private-unencrypted-export",
              "records": records, "collections": collections, "members": members, "tags": tags}
    if len(collections) > 100 or len(members) > 5000 or len(tags) > 5000:
        raise ValueError("Narrow the handoff; its metadata exceeds the portable import bounds.")
    if len(json.dumps(packet, ensure_ascii=False).encode("utf-8")) > MAX_BUNDLE:
        raise ValueError("This handoff exceeds 450 KB. Export a smaller collection; use encrypted backup for the full archive.")
    return packet


def import_bundle(conn, packet, validate_text, preview=False):
    if not isinstance(packet, dict) or set(packet) != {"schema", "created_at", "privacy", "records", "collections", "members", "tags"} or packet.get("schema") != SCHEMA:
        raise ValueError("Choose a Starlight library handoff v1 file.")
    if len(json.dumps(packet, ensure_ascii=False).encode("utf-8")) > MAX_BUNDLE:
        raise ValueError("The handoff exceeds 450 KB.")
    for key, bound in (("records", 999), ("collections", 100), ("members", 5000), ("tags", 5000)):
        if not isinstance(packet[key], list) or len(packet[key]) > bound:
            raise ValueError("The handoff has too many entries.")
    records, groups, members, tags = [], [], [], []
    seen = set()
    for row in packet["records"]:
        if not isinstance(row, dict) or set(row) != {"uid", "body", "kind", "captured_at", "last_seen_at", "source_app", "source_title", "device", "use_case"}:
            raise ValueError("A handoff capture has unexpected fields.")
        uid = identity(row["uid"])
        if uid in seen:
            raise ValueError("The handoff repeats a source identity.")
        seen.add(uid)
        if not isinstance(row["body"], str) or not row["body"].strip() or len(row["body"]) > 100_000:
            raise ValueError("A handoff original is empty or too long.")
        if not isinstance(row["kind"], str) or not isinstance(row["use_case"], str) or row["kind"] not in {"text", "prompt", "code", "url", "command", "path"} or row["use_case"] not in {"", "suno"}:
            raise ValueError("A handoff capture has an unsupported type.")
        for key, maximum in (("source_app", 80), ("source_title", 200), ("device", 80)):
            text(row[key] or "", maximum, key, True)
        for key in ("captured_at", "last_seen_at"):
            text(row[key], 40, key)
            from datetime import datetime
            if datetime.fromisoformat(row[key].replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("Handoff dates require an explicit timezone.")
        validate_text(row)
        records.append(row)
    group_keys = set()
    for group in packet["collections"]:
        if not isinstance(group, dict) or set(group) != {"id", "name", "description", "mode", "query"}:
            raise ValueError("A handoff collection has unexpected fields.")
        key = identity(group["id"])
        if key in group_keys:
            raise ValueError("The handoff repeats a collection identity.")
        group_keys.add(key)
        groups.append((key, collection_value(group)))
    for row in packet["members"]:
        if not isinstance(row, dict) or set(row) != {"collection", "uid"} or not isinstance(row["uid"], str) or not isinstance(row["collection"], str) or row["uid"] not in seen or row["collection"] not in group_keys:
            raise ValueError("A handoff membership has no source.")
        members.append((row["collection"], row["uid"]))
    tag_sets = {}
    for row in packet["tags"]:
        if not isinstance(row, dict) or set(row) != {"uid", "label", "source", "reason"} or not isinstance(row["uid"], str) or not isinstance(row["source"], str) or row["uid"] not in seen or row["source"] not in {"user", "agent", "local-rule"}:
            raise ValueError("A handoff tag has no valid source.")
        label = tag_name(row["label"])
        labels = tag_sets.setdefault(row["uid"], set())
        if label in labels or len(labels) >= 20:
            raise ValueError("A handoff repeats a tag or exceeds 20 tags per capture.")
        labels.add(label)
        tags.append((row["uid"], label, row["source"], text(row["reason"], 240, "Tag explanation")))
    added, reused, forks = 0, 0, 0
    for row in records:
        prior = conn.execute("SELECT body,kind FROM clips WHERE uid=?", (row["uid"],)).fetchone()
        if prior and (prior["body"] != row["body"] or prior["kind"] == "secret"):
            raise ValueError("A source identity has different content. Retain both handoff files for review.")
    if preview:
        for _, values in groups:
            if values[2] == "smart":
                clip_store.query_rows(conn, values[3], limit=1)
        return {"ok": True, "records": len(records), "collections": len(groups), "tags": len(tags),
                "privacy": "private-unencrypted-export", "state": "preview-only"}
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        mapping = {}
        for row in records:
            prior = conn.execute("SELECT id,body,kind FROM clips WHERE uid=?", (row["uid"],)).fetchone()
            if prior:
                if prior["body"] != row["body"] or prior["kind"] == "secret":
                    raise ValueError("A source identity has different content. Nothing was imported; retain both handoff files for review.")
                mapping[row["uid"]] = prior["id"]
                reused += 1
                continue
            body, app, title = row["body"], row["source_app"] or "", row["source_title"] or ""
            preview = " ".join(body.split())[:240]
            cur = conn.execute("""INSERT INTO clips(captured_at,last_seen_at,kind,source_app,source_title,sha256,char_len,
                preview,body,extra_json,device,uid,use_case,state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'saved')""",
                (row["captured_at"],row["last_seen_at"],row["kind"],app,title,hashlib.sha256(body.encode()).hexdigest(),len(body),
                 preview,body,json.dumps({"provenance":"private-library-handoff-v1","submission":"unknown"}),row["device"],row["uid"],row["use_case"]))
            clip_id = cur.lastrowid
            mapping[row["uid"]] = clip_id
            conn.execute("INSERT INTO clips_fts(rowid,preview,body,source_app,source_title,kind) VALUES(?,?,?,?,?,?)", (clip_id,preview,body,app,title,row["kind"]))
            conn.execute("INSERT INTO clip_occurrences VALUES(?,?,?,?,?,?)", (row["uid"]+":handoff",clip_id,row["captured_at"],app,title,row["device"]))
            conn.execute("INSERT INTO clip_jobs(clip_id) VALUES(?)", (clip_id,))
            added += 1
        group_map = {}
        for original_key, values in groups:
            key = original_key
            if values[2] == "smart":
                clip_store.query_rows(conn, values[3], limit=1)
            prior = conn.execute("SELECT name,description,mode,query FROM library_collections WHERE id=?", (key,)).fetchone()
            if prior and tuple(prior) != values:
                key = "import-" + hashlib.sha256((key+json.dumps(values)).encode()).hexdigest()[:32]
                forks += 1
                values = (values[0][:60]+" · imported", *values[1:])
            group_map[original_key] = key
            if not conn.execute("SELECT 1 FROM library_collections WHERE id=?", (key,)).fetchone() and conn.execute("SELECT count(*) FROM library_collections").fetchone()[0] >= 100:
                raise ValueError("The target supports up to 100 collections. Import a smaller handoff.")
            conn.execute("INSERT OR IGNORE INTO library_collections VALUES(?,?,?,?,?,1,?)", (key,*values,clip_store.now()))
        for key, uid in members:
            if conn.execute("SELECT mode FROM library_collections WHERE id=?", (group_map[key],)).fetchone()[0] == "manual":
                conn.execute("INSERT OR IGNORE INTO library_members VALUES(?,?)", (group_map[key],mapping[uid]))
        for uid, label, source, reason in tags:
            prior_labels = {row[0] for row in conn.execute("SELECT label FROM library_tags WHERE clip_id=?", (mapping[uid],))}
            if label not in prior_labels and len(prior_labels) >= 20:
                raise ValueError("A target capture already has 20 tags. Review its labels before importing.")
            conn.execute("INSERT OR IGNORE INTO library_tags VALUES(?,?,?,?,?)", (mapping[uid],label,source,reason,clip_store.now()))
    return {"ok": True, "added": added, "reused": reused, "collection_variants": forks,
            "state": "imported-locally", "sync": "manual-handoff"}
