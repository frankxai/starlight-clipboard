# Starlight music library and Suite integration, Codex, 2026-10-31, v1

Author and inline reviewer: Codex. Created: 2026-10-31. Revision: v1. Review state: local beta; independent provider, physical/native input and public-release acceptance pending. Source: Frank's CAIO implementation request, issue #4 and draft PR #5.

## Implemented outcome

The installed collector now supports personal music organization without changing retained originals. Four editable starter searches cover piano, cinematic, synth and ambient directions. A user can create manual collections or smart searches, combine multiple tag filters, edit labels and review local suggestions. The CLI supports agent-authored labels with provenance. No model is called automatically; local suggestions remain drafts until saved. User labels take precedence over an agent applying the same label.

Schema version 3 adds collections, memberships and labels to the existing SQLite store. Migration from version 2 does not invent source occurrences. Manual collections query indexed membership rather than expanding large identifier lists. Smart result counts are bounded at 1,000 and marked accordingly. Up to 100 collections and 20 tags per capture are supported. Optimistic versions reject stale collection updates. Window, vibe and tag drafts survive closing their editing surface; unsaved drafts are not crash-recoverable storage.

The portable handoff preserves original source IDs/dates, labels and collection definitions. Import validates before applying, commits atomically, reuses matching originals and rejects changed source content. Differing collection definitions become deterministic imported variants. Existing labels remain. Selected-vibe export excludes unrelated collection definitions. Unsupported fields, protected sources, credential-like originals and invalid bounds are rejected. Files are private, unencrypted and limited to 450 KB; a full encrypted archive backup is the larger recovery path. This is manual transfer, not continuous synchronization.

## Suite boundary

The active Nexus app-center source in `starlightintelligence.ai/apps/desktop/src/nexus/model.ts` already names Clipboard and Command Center. Its Rust `nexus.rs` adapter reads the private runtime binding and sends bearer-authenticated loopback requests to `/api/health` and `/api/raise`. It requests no original bodies. Clipboard retains that contract; `integrations/starlight-app.json` is a reference, not a new execution registry. The other session owns Nexus and installer files; no edits were made there.

The existing Command Center checkout contains another harness's unfinished changes. Its loopback health was unavailable during inspection. No claim is made that the complete Command Center/Nexus desktop suite has been installed or accepted by this slice. The source connector's request boundary is tested against the installed Clipboard independently of that UI.

Per-run native window titles prevent a new collector from reusing a stale window with an expired port/token after an upgrade. `/api/raise` now reports failure if the window did not open, and the CLI allows the bounded launch time. The Music shortcut requests the music view; a light visible-window navigation poll consumes that request without scanning the archive. Signed-in browser profiles are untouched.

## Verification

56 isolated Windows tests and source/installed self-tests pass. Coverage includes two-store handoff, repeat import, preserved source dates, source conflicts, stale edits, invalid records, tag bounds, authenticated API denial, preview before apply, full snapshot restoration and window placement/focus. Installer parsing and intent checks pass. JavaScript syntax and the final Impeccable scan on `board.html` and `library.js` pass with no findings.

Actual Chromium DOM with synthetic fixtures passed 45 desktop music, 46 mobile music, 47 desktop vibe-editor and 48 mobile organization assertions. Final v3 captures were visually inspected. Key events were dispatched programmatically, touch emulated and reduced-motion declarations forced for computed-style checks. These checks do not certify physical input, native Windows rendering or reboot behavior. An initial fixed-delay fixture assumption was replaced with waiting for actual result readiness; the failed evidence is retained privately. Narrow-screen inspection led to a shorter filter action and less supporting header text.

| Before | After | Why |
| --- | --- | --- |
| One music-candidate list | Editable personal vibes and multi-tag searches | Recover a specific creative direction without changing the source. |
| Music filing alone | Manual membership, provenance-bearing tags and reviewed suggestions | Users retain control of organization. |
| No portable library import | Validated preview, atomic merge and preserved variants | Transfer useful originals without overwriting local work. |
| Fixed window title across releases | Per-run identity and truthful open result | Avoid opening a stale authenticated window after upgrade. |
| Dense mobile header | Compact title/actions and one filter row | Leave more space for browsing. |

Selected/read/applied: Starlight SI for the single implementation lane, Emil design engineering, Impeccable and the existing DESIGN.md. Verified: stated source, API, synthetic interaction and rendered scopes. Independent provider review has no accepted verdict and remains a release gate. Previous provider attempts failed or timed out; new swarms were not admitted on this host.

## Remaining shared-platform work

Google/Microsoft account authority, continuous encrypted sync, device-key recovery/revocation and a signed public installer remain outside this working local slice. The existing desktop pairing contract documents platform device endpoints that are not implemented; this repo creates no competing account service. Follow the current estate storage/gateway registry before selecting hosted storage. The platform checkout's newer guide says not to expand R2; the prior R2 suggestion must not become an unreviewed deployment.

Full-suite launch acceptance, actual two-laptop use, reboot recovery, off-device backup/key custody and exact-revision independent review remain in issue #4. No cloud credentials, DNS, automatic upload, scheduled task or public release was activated. Private install, capture and recovery evidence stays under `.starlight/clipboard-index`.

Primary implementation reference: [SQLite transactions](https://www.sqlite.org/lang_transaction.html) and [online backup](https://www.sqlite.org/backup.html), retrieved through Context7 in this session. Source and integration instructions were explicitly read; routing checks and exclusive lanes record ownership, not runtime enforcement.
