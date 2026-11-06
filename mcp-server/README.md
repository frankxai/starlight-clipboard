# Starlight Clipboard MCP server

Stdio MCP server (`@modelcontextprotocol/sdk` 1.x, Node >= 22, pnpm) that exposes
the running local collector to agents. It reads `<CLIP_HOME>/data/panel.json`
(default `~/.starlight/clipboard-index`; written by `panel_file()` in `clip.py`) for the
port and token and talks only to `127.0.0.1` with `Authorization: Bearer <token>`.

| Tool | API | Kind |
| --- | --- | --- |
| `clip_search(query, limit)` | `GET /api/items?q=` | read |
| `clip_recent(limit)` | `GET /api/items` | read |
| `clip_get(id)` | `GET /api/detail` | read |
| `library_list(kind)` | `GET /api/library` | read |
| `clip_add(text, title?)` | `POST /api/add` | **write** |
| `clip_copy(id)` | `POST /api/copy` | **write** (replaces the system clipboard) |

Responses, including protected and `[redacted:...]` items, are passed through exactly
as the API returns them. If the collector is not running the tools return a clear error;
the server never starts it. `limit` is applied here because `/api/items` has no limit.

```sh
pnpm install && pnpm test && pnpm exec tsc --noEmit
node dist/src/index.js   # after pnpm build; register as a stdio server in your MCP client
```

Tests use a fake HTTP server and a temporary `CLIP_HOME`; no real clipboard is touched.
