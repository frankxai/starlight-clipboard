# Clipboard durable capture implementation
Author: Codex
Created: 2026-10-31
Revision: v1
Review state: local beta; independent provider review and rendered UI acceptance pending.
Source: issue [#4](https://github.com/frankxai/starlight-clipboard/issues/4), based on main revision 1cc2fd3baf9d50dce4713abb7067b85d620854b9.

## Delivered behavior

The existing Windows collector now retains captured records without the old age/row-count deletion policy. A copy and its occurrence, supported PNG payload and derived-export job commit in one SQLite transaction using WAL/FULL. Derived Markdown failures are retryable and do not roll back the source.

Repeated consecutive payloads keep occurrence timestamps. Migration retains old hit-count aggregates without inventing their dates. Original text up to the documented capture limit survives. A separate detail endpoint supplies the full retained text rather than silently limiting the preview to 8,000 characters.

The utility window uses a separate browser profile with sync and extensions disabled.

The palette adds date/app/use-case search, Suno candidates, saved/archive views, direct idea entry, explicit prompt-book and note filing, backup controls and recoverable error feedback. It preserves the existing restrained dark interface and system font.

Partial redaction drops associated rich HTML/pictures. HTML is independently checked, protected native formats/password-manager sources are excluded, and sealed private-vault export paths are refused. These are heuristics and boundaries, not a claim that every possible secret can be detected.

Terminal-wrap repair stores the original first and checks the clipboard sequence while holding the clipboard before replacing it. Self-paste suppression matches an exact sequence. The listener operates independently of shortcut registration and records known retry gaps.

The standard-library installer preserves previous launchers, takes a pre-upgrade snapshot, verifies immutable release hashes and self-tests the installed copy. Runtime data remains outside Git. The application uses existing Python and SQLite; no dependency, agent runtime or cloud gateway was added.

## Verification completed

- 21 isolated persistence/privacy/recovery/API tests pass.
- Built-in self-test passes.
- Controlled native Windows test captured ten stable test copies and restored the original supported clipboard content.
- A pre-upgrade snapshot of the actual local store restored into a separate directory with matching counts and SQLite integrity.
- Installed-store migration retained the existing archive; subsequent collector/health checks reported running, database integrity OK and no pending exports.
- JavaScript syntax and PowerShell parsing pass.
- Installed Impeccable detector returned no findings for the changed HTML.
- A 250-record isolated storage benchmark measured p95 ingestion of 9.17 ms and p95 search of 4.57 ms. These are local fixture database measurements, not UI latency or native clipboard throughput guarantees.
- The login shortcut points to the installed release launcher. A real reboot/sign-in test was not performed.

The native test and benchmark preceded the final midnight/repair-race hardening; those later paths are covered by dedicated passing regressions. The current source and installed release are bound by hashes in the private install/provenance receipts.

## Remaining acceptance

Rendered desktop/mobile, keyboard-focus, touch, reduced-motion and interrupted interaction checks remain pending. Browser admission was held by RAM reserve and the installed browse shim lacked its executable. No screenshot or visual-verification claim is made.

Independent provider review remains pending after the available review routes failed to return an accepted verdict. Attempts are diagnostic evidence, not an independent pass. Keep this branch/draft in beta and do not promote it as a fully verified public release.

Backups are consistent, checksummed, private local snapshots. Off-device encryption, recovery-key custody, automatic backup cadence and hardware-loss recovery remain separate work. No cloud inference, public prompt publishing or lossless multi-device protocol is claimed.

The existing prompt-book and one-note exports are wired. Writing a Markdown atom does not prove shared-memory reindexing or agent retrieval. Cloudflare enrichment, submission evidence, shared-plane registration and capability-catalog freshness remain open in issue #4.

## Source ownership and handover

One Codex writer owns this branch. The previous Grok branch and its merged terminal-wrap work were preserved. Source, tests and installer live in this repository; local databases, clipboard bodies, capability tokens and machine evidence stay private.

The estate handover belongs in frankxai/agentic-ops-hub at ops/sessions/2026-10-31.md, ops/OPS-LEDGER.md and ops/NEXT-PROMPTS.md. The lane checker found another active owner for those paths, so they were left untouched. Issue #4 remains the product pickup.

Emil design engineering and Impeccable were read and applied to the interface. Mechanical checks ran; rendered acceptance did not. Humanizer was applied to prose. Skill selection is not evidence of runtime verification.
