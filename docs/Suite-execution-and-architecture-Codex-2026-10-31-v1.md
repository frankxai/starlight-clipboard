# Starlight Suite execution and architecture, Codex, 2026-10-31, v1

Author: Codex. Created: 2026-10-31 UTC. Revision: v1.
Review state: inspected local beta; proposed shared-platform work; independent review pending.
Sources: Frank's CAIO execution request, Clipboard issue #4/PR #5, Nexus PR #240,
the inspected repositories and vendor references below. No new provider was activated.

## Decision and actual result

Keep the existing applications and connect their established boundaries. Clipboard
is the private capture/library utility; Nexus is the app directory and desktop
front door; Command Center is the operator workspace; SIS remains the memory
authority. Avoid another account service, memory database or orchestration daemon.

Clipboard source 787ba52119ce26c8a0249442c65ddff943ab9e7d is installed as
2026.10.31.6. All seven installed source hashes match. The collector retained
2,164 records, reported no pending exports and answered authenticated health with
retention=keep and cloud_processing=false. An unauthenticated health request
returned 404. Existing canonical memory and local encrypted backup bindings remain.
This metadata check did not establish that every historical copy was captured.

Music supports editable manual/smart vibes, tags with user/agent provenance,
date/app/text searches and reviewed local suggestions. A prior actual 26-original
handoff preserved source dates and repeated without duplicates in a separate
local store. That is manual transfer, not continuous two-laptop sync. The private
source installer ZIP already exists; it requires PowerShell7 and Python3.10+.

The approved npm download-cache cleanup removed only _cacache. Its measured
logical size was 7.79 GiB; observed free-space increase was 8.239 GiB while other
work ran. All 28 existing _npx directories remained. A later drive reading was
86.23 GiB / 9.06% free. Source, installed packages and clipboard data were outside
the deletion scope. Private receipt: Npm-cache-reclaim-Codex-2026-10-31-v1.json.

## Architecture alternatives

| Direction | User benefit | Cost and limit | Decision |
| --- | --- | --- | --- |
| Connect the existing Nexus, Clipboard and Command Center apps | Preserve the accepted music/capture experience and existing Node integrations | Several processes and separately qualified releases | Lead direction |
| Move all interfaces into one Tauri shell with a Node sidecar | One app window and potentially simpler distribution | Requires Command Center daemon extraction, capability isolation and migration proof | Later experiment after the connected suite works |
| Make the whole suite a hosted web app/PWA | Easy browser access and updates | Does not supply the persistent native Windows collector by itself | Useful remote view, insufficient as the capture architecture |

The native Windows clipboard remains usable through Win+V. Microsoft's built-in
history and same-account device sync are a serious low-effort alternative for
recent paste tasks; its documented history limit is 25 entries. Starlight's useful
distinction is the retained searchable archive, creative organization and explicit
memory filing. Cross-device Windows paste does not establish Starlight archive
sync or backup. No speed, savings or market-superiority claim was measured.
[Microsoft clipboard documentation](https://support.microsoft.com/en-us/windows/apps/using-the-clipboard).

## Windows installer execution

Existing Nexus source is 28810872d895b03e9d763aedafada718f26c2caf on PR #240.
An isolated qualification checkout now exists at
repos/.codex-worktrees/nexus-windows-qualification-20261031, branch
codex/nexus-windows-qualification-20261031. It preserves the other owner's checkout.
Rust 1.99.0, Cargo 1.99.0 and Visual Studio 2022 C++ Build Tools were discovered;
cargo fmt --check passed. This is formatting evidence, not native compilation.

GitHub run 41248702911 never started its test steps: its check annotation says
an Actions budget prevents further use. No matching Windows artifact exists.
No workflow was dispatched and no spending limit was changed.

Local PP briefly admitted one bounded build at 8,540 MiB free. RAM subsequently
fell below the 8,192 MiB requirement. A private dependency runner was prepared
with frozen-lockfile installation, a ten-minute timeout, process ownership,
storage checks and the 4 GiB runtime floor. Its first attempt failed before
spawning because PowerShell returned multiple Node paths; selecting the first
application corrected that runner. The next attempt refused on RAM admission.
No packages were installed by these attempts. The official CheckOnly script
later reported 4.97 GiB RAM, no owned dependencies, and admitted=false.

Next: obtain sustained host admission, install the frozen standalone dependencies,
run frontend checks plus locked native tests, build NSIS through the existing
bounded script, inspect the candidate hash/signature and exercise install/open,
Clipboard health/raise, update, rollback and reboot on Windows. Signing and public
publication remain separate gates. Tauri's current documentation confirms the
Windows MSVC/WebView2 prerequisites and Windows installer build route.
[Tauri prerequisites](https://v2.tauri.app/start/prerequisites/),
[Windows installer documentation](https://v2.tauri.app/distribute/windows-installer/).

## Two laptops and accounts: next implementation contract

Use one existing platform identity with Google/Microsoft sign-in and an approved
desktop grant. The desktop README still marks its device endpoints unimplemented;
reconcile that with actual account/recovery source before changing auth. A login
identifies an account; it does not recover encrypted content keys by itself.

Keep one SQLite store per device. Synchronize encrypted operations and immutable
objects with source UID, occurrence time and device identity. Make retries
idempotent; preserve conflicting collections as variants; make removals explicit
operations rather than silently deleting history. Do not file-sync a live SQLite
database/WAL. Device approval, revocation, offline edits, key recovery and loss of
one device must all have acceptance cases before calling this sync complete.

Use the existing platform's approved database/blob facilities after registry
reconciliation. The newer Nexus guide names Supabase Postgres and Vercel Blob and
says not to expand R2. Its required registry brief returned 404 and the local
architecture-stack reference was missing; those authority gaps are recorded,
not replaced by this document. No new cloud storage choice is approved here.

Private GitHub is appropriate for source and sanitized architecture. Keep raw
clipboard bodies, databases, recovery keys and personal prompt bundles outside Git.
MD/JSON are useful exports; Notion and Drive should be explicit projections or
transfer destinations, not competing archive authorities. The current JSON handoff
is unencrypted and limited to 450 KB. Local restic snapshots do not establish
off-device recovery or independent password custody.

## Classification and current technology discovery

Retain the current local rules as the default. An optional decision layer can
suggest prompt/music/idea categories and use-case tags, then abstain when uncertain.
The user's labels take precedence. Neither classification nor a copy proves a
prompt was submitted to Suno or produced a successful song. Classification must
never authorize deletion or external publishing.

Cloudflare's Clef and Clef-flash are decision models. Clef-omni extends that family
to multimodal input; TypeSafe's Jev is also available through Cloudflare. These
are relevant evaluation candidates for bounded routing/classification. They are
not installed or approved in Starlight by this investigation. I found no verified
Cloudflare model called System 0 in the official material checked.
[Clef launch](https://blog.cloudflare.com/clef-decision-models/),
[Clef family update](https://blog.cloudflare.com/clef-faster-cheaper-multimodal/),
[Jev on Cloudflare](https://developers.cloudflare.com/ai/models/typesafe/jev/).

Before activation, use a synthetic or explicitly approved labeled corpus, compare
against the local baseline, measure per-label precision/recall, abstention,
latency and cost, and review payload/logging boundaries. Keep external processing
off until the provider, route, budget and consent are concrete. The existing
gateway authority remains in force; this creates no second gateway.

Context7 is available in this Codex session and was exercised for current Tauri
installer documentation. Use the existing estate registry and skill/tool indexes
to discover capabilities, then retrieve vendor docs when a dependency is used.
A bounded manifest can record source URL, checked date, supported operation and
review state. Installed tools do not imply active services, and a static index
cannot guarantee awareness of every newly released technology.

## Remaining acceptance

Command Center health on 127.0.0.1:4321 was offline. Its primary checkout and the
older installed CLI worktree contain other harnesses' unfinished source; neither
was changed or launched. Full Suite integration, a compiled Windows candidate,
actual second-laptop sync, off-device restore/key custody, independent exact-head
review and clean install/reboot/update tests remain open. No public release,
cloud upload, account activation, new scheduler or paid inference was performed.

Private machine receipts are under .starlight/clipboard-index. Durable continuation
belongs in agentic-ops-hub and Clipboard issue #4. All statements above distinguish
observed behavior, existing earlier evidence and proposed work.
