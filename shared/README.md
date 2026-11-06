# Shared shapes

`clip-item.schema.json` (JSON Schema 2020-12) describes `ClipItem`, `Combo` and
`Prompt` plus the `/api/items`, `/api/detail`, `/api/library`, `/api/add` and
`/api/copy` responses.

**`clip.py` is the source of truth** (with `clip_store.py` and `clip_library.py`).
The schema is derived from the SQLite columns and the API handlers there and
invents no fields. If they disagree, the Python wins and this schema is the bug.
`Combo` is the library collection; `Prompt` is a ClipItem with `kind: "prompt"`.
