# Starlight Clipboard

A private Windows clipboard archive with a shortcut palette and searchable prompt library. It listens beside Windows clipboard history and keeps Win+V available.

Open **Starlight Clipboard** from the Start menu, or press **Ctrl+Alt+V** while capture is running. Your copies stay on this PC. Cloud inference and external publishing are disabled.

Open **Starlight Music** from the same Start-menu folder, or run `clips music`, for the music workspace. Both entry points use the same collector and retained originals.

## Install

Requires Windows, PowerShell 7 and Python 3.10 or newer. No pip packages, Node build, account, or API key is required.

```powershell
./install.ps1 -WhatIf
./install.ps1 -Start
```

The installer takes a consistent pre-upgrade database snapshot, preserves previous launchers, verifies the copied release with its self-test, migrates existing records, and installs an immutable release under:

```text
%USERPROFILE%/.starlight/clipboard-index/runtime/releases/<content-hash>/
```

Your existing database remains at `data/clips.sqlite` under the same runtime root. Private prompt books remain in `%USERPROFILE%/.starlight/prompt-fabric`. The existing `%USERPROFILE%/.local/bin/clips.cmd` opens the selected release. Start-menu shortcuts open the library or start capture.

The installer refuses to replace a running collector. Use `clips stop` for the known Clipboard process before upgrading. It never kills a browser or another task.

Starting automatically at login is a separate, explicit option:

```powershell
./install.ps1 -EnableStartup
```

This adds a per-user Startup shortcut. It does not register a service or scheduled task. Follow the operator's startup-approval policy before using that option.

## Find and keep ideas

The palette has Recent, Prompts, Suno candidates, Saved, Archive and All history views. Select a local date or use filters:

```text
use:suno after:2026-10-01 before:2026-11-01
type:prompt app:chrome
state:saved piano
state:any on:2026-10-31
device:my-pc
```

Dates are interpreted in the local Windows timezone. `after:` includes the start of the date; `before:` excludes it. `on:` selects one local calendar day. Free-text searches include archived content unless a state filter says otherwise.

Arrow keys select; Enter pastes; Ctrl+Enter saves the selected text to the private prompt book; Ctrl+P toggles pin; Escape hides the palette. Ctrl+K focuses search and Alt+N opens the idea composer. Inside the composer, Ctrl+Enter saves the idea. Buttons also support touch and keyboard navigation. Save idea writes a note directly without replacing the system clipboard.

The liquid-glass library groups captures by last-seen date and keeps the original capture date in the reading pane. Search by text, date or app; use the shield button for capture, memory and backup health. The reading pane shows the full retained original, including longer text and code. Narrow windows use a separate reader with a Library return button.

An interrupted search cannot paste its previous result. Connection failures offer Retry. Unsaved idea text survives hiding the composer; saving an earlier draft preserves edits made while that save was pending. Drafts remain in the window until saved or discarded. They are not recovered after a process crash.

Archive changes visibility. Restore returns an archived capture to Recent. Records are no longer automatically deleted because of age or row count. Clipboard copies of files preserve their paths, not the referenced files themselves.

## Music vibes and portable libraries

Music includes four editable starter searches: Midnight piano, Cinematic ascent, Neon motion and Deep focus. Choose **New vibe** for a hand-picked collection or a saved search. Smart searches can combine tags, for example `use:suno tag:piano tag:intimate`. **Organize** on a retained text capture edits its tags and manual membership. Removing membership retains the original.

**Suggest tags** proposes labels using local wording rules. Suggestions remain a draft until saved. The agent CLI also accepts provenance-bearing labels; user choices take precedence over an agent applying the same label. No external model is called automatically.

```powershell
clips library list
clips library create --name "Rain room" --description "Piano sketches for the next project"
clips library create --name "Quiet piano" --mode smart --query "use:suno tag:piano tag:intimate"
clips library tag --id 12 --tags piano intimate
clips library suggest --id 12
clips library assign --id 12 --collection <collection-id>
clips library export --collection <collection-id> --file <new-private-file.json>
clips library import --file <private-handoff.json>
```

**Move library** exports selected originals, labels and collection definitions. Selecting a vibe limits the export to that vibe and its matching originals. Without a selected vibe, export includes matching music prompts and library definitions. Files are private and unencrypted, bounded to 450 KB; use an approved encrypted transfer channel. On the second installation, choose the file, inspect its validated counts and select **Import**. New imported originals appear in Saved.

Import retains source identities and dates, reuses matching originals and refuses conflicting source content. Differing collection definitions become explicit imported variants. Existing local labels remain. Repeating a handoff is idempotent. Import is atomic and rejects unsupported fields and protected sources. This is a manual handoff; automatic sync, account login, revocation and encryption-key recovery remain a separate shared-platform stage. Full encrypted snapshots include the collections and labels.

The existing Nexus app-center connector uses authenticated `/api/health` and `/api/raise` against the private runtime binding. It never requests original bodies for inventory. [The integration reference](integrations/starlight-app.json) documents the fixed companion identity and CLI. No parallel app center or account authority is installed here.

## Commands

| Command | Purpose |
| --- | --- |
| `clips` | Show recent captures |
| `clips search use:suno piano` | Search content and metadata |
| `clips add "An idea to keep"` | Save an idea explicitly |
| `clips prompts` | List prompt candidates |
| `clips promote 12 --scope starlight` | Save selected text to a private prompt book |
| `clips remember 12` | File one note in the permitted local memory vault |
| `clips archive 12` / `clips unarchive 12` | Hide or restore a capture |
| `clips resolve 12` | Mark handled while preserving the record |
| `clips doctor --json` | Read capture, export and backup health without printing payloads |
| `clips backup` | Create a consistent local snapshot with checksums |
| `clips integrations --memory --backup` | Bind the existing canonical memory and local encrypted backup installations |
| `clips integrations` | Inspect integration and daily-backup status |
| `clips backup --encrypted` | Save a consistent snapshot to the configured existing restic repository |
| `clips recover-encrypted <snapshot-id> --target <new-directory>` | Verify and restore one encrypted Clipboard snapshot into a new store |
| `clips restore <snapshot-folder> --target <new-directory>` | Verify and restore into a new directory |
| `clips export --query "use:suno" --destination <new-file.jsonl>` | Export up to 999 matching private text records |
| `clips reindex` | Refresh deterministic music hints and retry derived-file exports |
| `clips watch` / `clips stop` | Start or gracefully stop capture |
| `clips self-test` | Run isolated built-in checks |

Backups are private, unencrypted local snapshots. They protect against an upgrade or database error, not loss of the computer. Copy a completed snapshot through your approved encrypted backup system for off-device recovery. A live SQLite database/WAL must not be shared between machines through a file-sync folder.

Restore refuses an existing destination and checks the manifest and database before creating the new store. Source originals and transactional image payloads survive; Markdown sidecars are rebuildable caches. No old snapshot is automatically deleted.

## Capture and privacy

Capture uses native Windows notifications and attempts a bounded snapshot promptly. Locked clipboard data is retried only while its sequence is unchanged; a known failed or superseded retry is reported. Windows notifications do not provide a historical payload feed: periods while stopped and content overwritten before a read remain possible gaps.

Text up to one million characters is retained. Larger values are marked incomplete. Pictures use supported PNG/bitmap formats. Native protected-history markers and password-manager sources are excluded. Secret patterns are redacted before storage, and rich HTML is independently checked. Partial secret redactions discard the associated HTML and picture so hidden representations do not preserve the excluded text. These rules cannot identify every possible sensitive value or screenshot.

Each new occurrence of a repeated consecutive payload keeps its timestamp. Historical hit counts remain aggregates; migration does not invent lost historical dates. The SQLite transaction includes the capture, occurrence, transactional picture and pending export job. Sidecar failures leave a retryable job and the committed original. WAL uses full synchronous durability.

The existing terminal-wrap repair stores the eligible original before changing the pasted representation. Self-paste suppression matches a Windows clipboard sequence, so it does not ignore unrelated copies during an arbitrary time window.

## Prompts, Suno and memory

Music hints use local rules. A short style string with instruments and BPM can be a prompt candidate. The Suno label suggests a use case; it does not prove where a prompt was submitted or that it produced a successful song. Missing BPM stays unknown. No model inference runs.

Prompt books retain the original capture, stable source UID and source date. Repeated promotion is idempotent for that source. Public `frankxai/prompt-library` remains a separate reviewed corpus; nothing is pushed there.

Music candidates save to the private `suno-music` book from the library window or
`clips promote <id>` using automatic scope. Explicit `--scope` choices remain
available. A source can belong to more than one private book without duplicate
entries in the same book. File identities hash the full source UID so migrated
records that share an ID prefix cannot overwrite one another.

With canonical memory configured, `clips remember` uses the existing Starlight Memory writer with its bound vault and tenant, then verifies the source UID, content hash and retained text through the authenticated shared reader. The writer starts only for this operation and exits afterward; embeddings stay off. The interface distinguishes verified recall from a stored note awaiting verification. Receipts prevent duplicate filing, including uncertain write outcomes. Source changes require review and rebinding. Notes over 12,000 characters require a shorter selection; their full source remains in the archive.

Without that binding, `clips remember` exports one local Markdown atom beneath the Clipboard runtime. An explicit `STARLIGHT_VAULT` can select a permitted export destination. It does not automatically write into the canonical repository. Sealed `private/` or private-vault paths are refused, including resolved links. A local export does not prove shared indexing or agent retrieval.

Run `clips integrations --memory --backup` to bind installations that already exist on this machine. The memory reader must report the same canonical vault and tenant as the writer. The backup binding uses existing `STARLIGHT_RESTIC_REPO` and `STARLIGHT_RESTIC_PASSWORD_FILE` references. Credential contents are never copied into configuration. This command creates no account, repository, global MCP registration or scheduled task and refuses remote backup setup.

After backup binding, the existing collector attempts a consistent snapshot and encrypted copy once per day while running. A failed attempt is recorded and retried no more than once per hour. The Back up button runs the same operation. Retention is manual; no snapshot is pruned. Existing writer locks are preserved. Check `clips doctor --json` for the last cycle and encrypted snapshot.

Encrypted recovery accepts only a snapshot tagged by Clipboard, restores its leaf subtree into isolated staging with restic content verification, checks the Clipboard manifest and SQLite integrity, and requires a new target. This avoids replaying Windows ancestor directory permissions. Interactive restore is bounded to 512 MiB; larger archives need the existing backup operator. An encrypted repository on this computer still requires a separately configured off-device destination and independent password custody for hardware-loss recovery.

The utility window uses its own profile under ui-profile with browser sync and extensions disabled; it does not use your signed-in browser profile.

The local API binds only to 127.0.0.1 on a random port and requires a per-run capability token. It checks Host and browser Origin, limits JSON request bodies, and uses no-store and restrictive response headers. A local token holder can read stored content; do not publish `data/panel.json` or expose the port.

## Architecture and next stages

Keep this collector and its data local. SIS/local_core owns trusted-memory identity and promotion policy. Existing shared memory services provide agent retrieval. Notion and Drive can receive reviewed projections; they are not capture dependencies.

Cloudflare Clef/Clairic, optional browser submission receipts, encrypted multi-device synchronization, a pooled raw-Clipboard MCP backend and a Rust/Tauri comparison remain separate implementation stages in [issue #4](https://github.com/frankxai/starlight-clipboard/issues/4). Canonical memory filing and recall use the existing memory tools. Existing legacy peer snapshots are not a verified lossless synchronization protocol.

The installed Context7 and capability inventories remain owned by their existing systems. This application does not install another global model gateway, architecture catalog, agent runtime or scheduler.

## Verification

```powershell
py -3 -m unittest discover -s tests -v
py -3 clip.py self-test
```

Tests use isolated temporary stores and fixtures, including recovery, protected sources, long originals, archive/search, full-text API previews, authorization, sequence suppression and failed exports. `tests/ui_fixture.py` produces an explicitly synthetic standalone preview; its optional browser driver checks focus, interrupted searches and drafts, disabled actions, viewport containment, touch target sizes and reduced-motion declarations. These checks do not certify real Windows clipboard coverage, physical input, reboot recovery, off-device backup or production deployment.

Implementation author: Codex · 2026-10-31 · v4. Design tokens and review scope are in [DESIGN.md](DESIGN.md) and [the design review](docs/DESIGN-REVIEW-Codex-2026-10-31-v1.md). Exact source/review/install receipts belong with the task evidence; local private data never belongs in Git.
