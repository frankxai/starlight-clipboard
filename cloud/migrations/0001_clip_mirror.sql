-- STAGED, NOT APPLIED. No D1 database exists; nothing runs this file automatically.
-- Mirrors shared/clip-item.schema.json, which is derived from clip.py (source of truth).
-- Deliberately has no `body` column: clipboard bodies can hold secrets and what syncs is the owner's decision.
CREATE TABLE IF NOT EXISTS clips (
  uid TEXT PRIMARY KEY,
  captured_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('text','url','path','command','prompt','code','image','secret')),
  source_app TEXT,
  source_title TEXT,
  sha256 TEXT NOT NULL,
  char_len INTEGER NOT NULL,
  hit_count INTEGER NOT NULL DEFAULT 1,
  pinned INTEGER NOT NULL DEFAULT 0,
  preview TEXT NOT NULL,
  device TEXT,
  use_case TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','saved','resolved','archived'))
);
CREATE INDEX IF NOT EXISTS clips_kind_seen ON clips(kind, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS clips_state_use ON clips(state, use_case);

CREATE TABLE IF NOT EXISTS library_collections (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('manual','smart')),
  query TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS library_members (
  collection_id TEXT NOT NULL REFERENCES library_collections(id),
  clip_uid TEXT NOT NULL REFERENCES clips(uid) ON DELETE CASCADE,
  PRIMARY KEY (collection_id, clip_uid)
);

CREATE TABLE IF NOT EXISTS library_tags (
  clip_uid TEXT NOT NULL REFERENCES clips(uid) ON DELETE CASCADE,
  label TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('user','agent','local-rule')),
  reason TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (clip_uid, label)
);
