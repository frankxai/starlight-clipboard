# Starlight Cloudflare execution, Codex, 2 November 2026, v1

Author: Codex. Created: 2026-11-02 Europe/Amsterdam. Revision: v1.
Review state: implementation candidate; independent/native/private-preview acceptance pending.
Source: Frank's request to implement and activate Cloudflare across the existing vision;
Clipboard issue #4/PR #5; source d86a076; live read-only Cloudflare inventory and the
official documentation linked below. Private machine receipts stay outside Git.

## Useful outcome and decision

Make the phone capture surface installable from trusted HTTPS, preserve device-local
originals, and provide a bounded typed classifier through the already-created
Starlight gateway. Reuse the existing Suite and account authority. Activation means
a tested capability with recovery and funding understood; it does not mean enabling
every Cloudflare service.

The alternatives include the accepted Vercel baseline:

| Direction | Benefit | Material cost/limit | Decision |
| --- | --- | --- | --- |
| Microsoft transport with existing local archives | Fast text handoff using the current Windows setup | Latest clip is temporary; no creative library or complete backup | Retain as optional transport |
| Existing Vercel product hosts the phone surface | Preserves accepted experience-plane ownership | Needs its product owner's route/auth integration; no measured comparison yet | Keep as the production baseline |
| Small protected Worker delivering the current mobile app; selected Clef requests | Reuses the completed mobile surface and existing gateway, with no new data store | Access app, runtime/phone acceptance and inference funding need qualification | Implement this slice |
| A new hosted agent/database/search/sync platform now | Could unify many future features | Duplicates authority, exposes private data and adds unqualified spend/recovery work | Do not introduce it |

## Current account evidence

The connected account has nine Workers. Existing names include
starlight-cloud-worker, starlight-execution-dev, starlight-fleet-ingress and the
Starlight site pilot. These are existing services with their own owners; none was
replaced or reconfigured by the Clipboard change.

The existing starlight-agent-lab AI Gateway has authentication on, collect_logs
false, cache TTL zero and a five-request/60-second sliding limit. Its reported
Workers AI billing mode is postpaid. An existing Access organization has no Access
applications. The connection's subscription read returns 403. A startup-program
memory record is advisory and does not prove credits apply to a specific route.
No inference was invoked and no funding, credentials, top-ups or budget changed.

The Nexus agent-plane source distinguishes native Workers AI from optional Vercel
Gateway routes and explicitly warns about separate billing. The generated registry
brief and architecture-stack pointers remain unresolved, but the actual accepted
architecture decisions were read directly from agentic-ops at 316f194c. They retain
Vercel as default experience plane and multi-provider gateway. This Cloudflare
mobile/model candidate is Frank's requested trial; its production exception still
requires Registry review and a measured reason. It does not replace estate-wide
gateway/storage doctrine or expand R2. Current APIs and model
request/output schemas were retrieved from Cloudflare in this session.

Another active Codex lane owns the estate-wide Cloudflare rollout and shared hub
files. Its in-progress plan is at the ci-cost-hub-20261031 worktree,
ops/plans/Cloudflare-rollout-Codex-2026-11-02-v1.md (initial inspected SHA256
e5a5a130c237221c4ee0b93c57f63a4d46e84bc55af1f73f78c6421b5d48ffdb,
uncommitted at inspection). It is an advisory peer draft, not an accepted ruling.
This slice does not overwrite its files or attach executors to its queues.

## Implemented artifact

`cloud/` contains a Worker, official jose-based Access verification, a selected-text
Clef classifier, a strict seven-file packaging allowlist and a dependency lockfile.
Its ESM bundle includes the actual current mobile source and the reused Starlight
icon. No database, capture, token, browser profile, private export or nested source
directory is included. It emits a valid inspectable multipart version-upload body
and hashes. There is no blind recursive copy or automatic deployment.

The host refuses POST shares without consuming the body. A valid installed mobile
worker handles incoming shares locally. Static app files require Access even if an
unprotected workers.dev URL is accidentally exposed. JWT verification fixes the
issuer/key endpoint and validates audience, signature, dates and supported identity.
The host cannot use Access revocation to wipe offline browser data.

Inference is off in the shipped metadata, with no AI binding. Enabling it additionally
requires the actual Access app, approval reference, fixed origin and rate-limit/AI
bindings. Requests require per-selection consent, reject unknown fields and known
credential patterns, and impose byte/text bounds. Only typed classifications are
returned; uncertain results never become applied tags. Model content cannot authorize
shell work, archive deletion or memory promotion. The mobile UI has no remote-model
button yet; capture remains independent of the classifier endpoint.

The optional classifier is wired to the inspected existing gateway, with caching
and request logging disabled. This is not a measured model-quality or cost claim.
No model fallback can silently change the provider or funding source. Rate limits
are not a hard monthly spend cap. An approval-reference variable is configuration,
not a runtime human-approval enforcement mechanism.

## Ordered execution across the vision

| Stage | Owning existing product | Concrete next artifact | Acceptance |
| --- | --- | --- | --- |
| 1. Reliable capture/recovery | Clipboard | Keep Windows v7; qualify this protected mobile delivery | Real phone share/offline/recovery; signed-in and denied requests; exact bundle receipt |
| 2. Native phone | Clipboard mobile stage | Expo UI and SQLite/SQLCipher adapter for the existing portable contract | Encrypted migration, interrupted writes, Android share activity, SecureStore loss/recovery |
| 3. Trusted devices | Existing Starlight platform/Nexus | Reconcile existing grants, approve/revoke devices and sync encrypted operations | Actual second laptop, clock skew/retry/conflict, revoked device and wrong-workspace denial |
| 4. Creative continuity | Clipboard/Music and existing prompt library | Link retained original, prompt revisions, chosen vibe and actual track/result | Find a known old Suno direction and reuse it; creator comparison against current workflow |
| 5. Curated knowledge | Existing SIS/memory and research-intelligence-os | Explicit promotions and provenance-bearing retrieval; inspect current research pipeline PR #7 | Cross-agent recall of selected evidence; excluded private clips never enter a corpus |
| 6. Suite distribution | Existing Nexus/Command Center installer work | Qualify the existing bootstrap/native installer, update and rollback | Clean Windows install, reboot, deep links, uninstall/data preservation and recovery |
| 7. Estate operations | Existing Command Center and agentic-ops registry | Device/job capability receipts, product health and review queue | No phone library token grants shell execution; stale/offline states visible |

Keep Windows originals as the durable local source; MD/JSON/Drive/Notion are reviewed
exports. Keep private GitHub for source and sanitized contracts. Never sync live
SQLite/WAL files as an archive protocol. Native content encryption requires tested
independent key recovery. A Google/Microsoft account login does not recover keys by
itself. Preserve other harnesses' work and existing product boundaries.

Cloudflare services have distinct jobs: Workers deliver approved interfaces and
bounded APIs; the existing AI Gateway controls selected inference; existing agent
runtimes own authorized jobs; existing Workflows/Queues handle durable work only
after their product contract and funding are admitted. Search/vector storage is
derived from an approved corpus, never a default sink for all clipboard contents.
No service is activated merely because it is available.

## Verification and release state

Node tests exercise actual Worker request handlers, real RSA/JWKS validation,
wrong audience/issuer/time/signature denial, no body read on denied shares, exact
origin, rate denial, typed provider request, output validation and private errors.
The packaging tests execute the actual ESM bundle, parse its multipart artifact,
check hashes and prove nearby private canaries are excluded. These checks do not
establish native Cloudflare execution or physical Android acceptance.

The existing Windows collector and memory/backup settings remain active. Its
history helper correctly reports deferred-memory when the reserve is unavailable.
No installed desktop capture code changes in this slice. No new image generation,
visual redesign, Expo runtime, scheduler, raw-data upload or autonomous fanout occurs.

Consequential release requires exact-head independent review, native Worker/HTTPS
tests, a narrow approved Access policy, physical phone acceptance and reviewed
payload-free observability. Native builds/review remain subject to the machine
floor. Public launch, inference funding and actual encrypted device sync remain open.
Use issue #4 and the agentic-ops-hub ledger for continuation; keep PR #5 draft.

## Primary references retrieved 2026-11-02

- [Workers version upload API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/)
- [Cloudflare Access JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/)
- [Clef model and typed schema](https://developers.cloudflare.com/workers-ai/models/clef/)
- [AI Gateway Worker bindings and logging/cache options](https://developers.cloudflare.com/ai-gateway/usage/worker-binding-methods/)
- [Gateway spend limits](https://developers.cloudflare.com/ai-gateway/features/spend-limits/)
- [Cloudflare CLI build/preview semantics](https://developers.cloudflare.com/cf/projects/)
- [Accepted architecture decisions](https://github.com/frankxai/agentic-ops/blob/316f194c6e0853e86845b5c4948ce9d0b510b03d/registry/architecture_decisions.yaml)

The live model schema API was inspected without inference. jose/esbuild versions,
integrity metadata and MIT licenses were retrieved from the npm registry. Installed
cf 1.0.0-beta.21 and Wrangler 4.152.0 were discovered; this package uses the API
artifact and introduces neither configuration system nor a CLI upgrade.
