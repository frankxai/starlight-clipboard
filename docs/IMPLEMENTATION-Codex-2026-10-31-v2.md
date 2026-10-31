# Clipboard memory and encrypted recovery, Codex, 2026-10-31, v2

Author: Codex. Created: 2026-10-31. Revision: v2.
Review state: installed local beta; independent provider and rendered interface acceptance remain pending.
Predecessor: IMPLEMENTATION-Codex-2026-10-31-v1.md, retained unchanged.
Source base: 6d852064b2d79dcda6f224b5c2438e7e771ed7b0; issue #4 and draft PR #5.
The private installation receipt binds the final source revision and installed file hashes.

## Outcome

Explicit memory filing now uses the existing canonical Starlight Memory writer
on demand, with embeddings off, a pinned source binding and the vault/tenant
reported by the authenticated shared reader. It verifies source UID, body hash
and retained text through that separate reader. A live source-linked implementation
note was written and retrieved again through the existing agent memory tool.
No global gateway or resident memory service was added or restarted.

Per-source receipts and exclusive leases prevent concurrent duplicate filing.
An uncertain writer outcome requires reconciliation before another write. A stored
receipt survives a failed recall check and can be verified later without rewriting.
Sealed vault paths, secret events, mismatched reader identity and overlong notes
are refused. Full originals stay in SQLite. Unconfigured installations export to
their own local memory-atoms directory rather than guessing a canonical repo path.

The existing restic repository and password-file reference are bound locally.
The application creates a consistent SQLite snapshot and encrypts it in that
repository. It never initialises a repository, prunes snapshots or clears another
writer's lock. The existing collector attempts this once per day while running;
failed attempts have an hourly retry bound and a visible receipt. The Back up
button uses the same operation. No scheduled task was registered.

Encrypted recovery requires a new destination, an explicit Clipboard-tagged
snapshot and a bounded size. It verifies restic contents, the Clipboard manifest
and SQLite integrity. The first Windows recovery attempt exposed ancestor ACL
replay onto staging. Recovery was corrected to restore the leaf subtree only;
the subsequent real restore matched record/occurrence counts and logical content
hashes. The failed staging evidence was preserved.

## Verification

- 38 isolated regression tests and the built-in self-test pass.
- Real canonical memory filing and a subsequent agent-tool read pass.
- Repeating the same filing reuses its recorded identity; isolated tests cover unknown outcomes and reader failure.
- A real encrypted snapshot restored separately with matching source content, records and occurrences.
- PowerShell parsing, Python compilation, JavaScript syntax and Impeccable checks pass.
- Installation uses immutable releases and preserves the earlier beta and pre-upgrade archive.

The live memory operation used the existing canonical writer as an application
data operation. The separate source-routing check refused implementation on the
vault's main branch. No vault source files were edited, staged or committed; its
existing dirty notes and source branch were preserved. Publication/sync remains
the vault owner's operation.

## Remaining acceptance

The encrypted repository is on the same computer. Hardware-loss recovery and
independent password custody remain unverified. Remote setup is refused by this
local binding command and needs the existing backup owner's destination and access.

Automatic approval review blocked a browser-inspection command under fleet policy.
Computer Use's native pipe was unavailable. No rendered UI, keyboard, mobile or
touch verification is claimed. Independent provider acceptance and a real reboot
remain pending; keep the PR in draft.

Cloudflare enrichment, browser submission evidence, multi-device replication and
a pooled raw-Clipboard MCP backend remain separate work. A Suno candidate still
does not establish prompt submission or generation success. Context7 and the
architecture/capability inventories retain their existing owners.

## References

- [Product issue #4](https://github.com/frankxai/starlight-clipboard/issues/4)
- [Draft source PR #5](https://github.com/frankxai/starlight-clipboard/pull/5)
- Canonical writer: starlight-memory/src/mcp/server.mjs and vault-store.mjs; deployed shared tool plane read contract.
- [MCP transport specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [restic backup documentation](https://restic.readthedocs.io/en/stable/040_backup.html)
- [restic restore documentation](https://restic.readthedocs.io/en/stable/050_restore.html)
