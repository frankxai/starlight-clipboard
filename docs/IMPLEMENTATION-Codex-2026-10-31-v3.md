# Clipboard library identity fixes, Codex, 2026-10-31, v3

Author: Codex. Created: 2026-10-31. Revision: v3.
Review state: local beta; independent provider and rendered acceptance pending.
Predecessors: v1 and v2 implementation reports, retained unchanged.
Source base: 6c3f18423efff98b14e5610732df50f78124d2e2; issue #4 and draft PR #5.

Follow-up inspection found that migrated source IDs share a prefix. Using only
that prefix in local note names could overwrite distinct occurrences with equal
content. Filenames now hash the complete source UID. A reproducing regression
failed before the fix and passes afterward.

Music candidates route to a private suno-music book from the UI and automatic CLI
scope. Promotion receipts are resolved per destination; one source can be in two
books while repeated filing in one book remains idempotent. A writer lease protects
book indexes. Existing entries and source text remain intact.

Memory preflight refusals now distinguish a writer that never started from an
uncertain write outcome. Repairing a source binding can retry the former; the
latter still requires reconciliation before another canonical write.

41 isolated tests and the built-in self-test pass. The existing shared reader
retrieved the live source-linked memory note. Real encrypted backup and a separate
content-verified restore passed in v2; the installed API verified both memory
recall and backup creation. Final installation hashes and version are recorded
privately after upgrade.

The bounded Grok review of the v2 source timed out without an accepted verdict.
It does not verify this revision. Browser inspection was blocked by automatic
approval review under fleet policy; Computer Use's native pipe was unavailable.
Rendered desktop/mobile/keyboard/touch checks and a real reboot remain pending.
Encrypted backup is local; off-device recovery and independent key custody remain
unverified. Keep the source PR in draft.
