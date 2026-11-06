# Cloudflare delivery and selected classification

Author: Codex. Created: 2026-11-02. Revision: v1.
Review state: implementation candidate; account activation and independent review pending.

This Worker hosts the existing mobile companion while its originals and drafts
remain on the device. It can classify an explicitly selected text through the
existing `starlight-agent-lab` gateway. It never reads a desktop archive, receives
background clipboard uploads, applies model suggestions or creates storage.
The mobile UI does not yet expose the remote classifier.

## Build and verify

Node 22.18+ is required. From `cloud/`:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
npm test
```

The pinned dependencies are MIT-licensed jose 6.2.15 for Cloudflare-recommended
JWT verification and esbuild 0.28.2 for packaging. No global runtime or SDK upgrade
is required. No cf/Wrangler project configuration is generated or migrated.

From the product root, choose a fresh private output leaf whose parent exists:

```powershell
node cloud/package.mjs C:/Users/frank/.starlight/clipboard-index/cloud-candidate-20261102 <verified-commit>
```

The packager reads only seven named mobile files and rejects symlinks/oversize
assets. It embeds them into an ESM Worker, changes the generated shell-cache name
when its source assets change, and writes the Worker, API metadata, exact multipart
upload bytes and SHA256 manifest. It refuses an existing destination. The original
mobile source is untouched. The shell cache contains public application files;
originals remain in IndexedDB. Old cache pruning is deliberately not automatic.

`version-upload.multipart` is an API request artifact, not a deployment receipt.
Its metadata has inference disabled and no AI, storage, rate-limit or Access
bindings. The manifest names the version-upload endpoint; promotion to traffic,
Access application/policy, preview exposure and approved inference are separate
operations. No script uses the deprecated automatic default gateway.

## Boundary and responses

- `GET /api/health`: payload-free capability metadata. No authentication claims,
  archive counts, account IDs, credentials or device identities.
- Seven public source assets: require a cryptographically verified Cloudflare
  Access app JWT. Missing issuer/audience fails 503; invalid/missing token is 401.
- `POST /share`: returns 428 without reading or forwarding the body. An installed
  phone service worker must save the share locally. An inactive worker cannot
  cause server-side capture.
- `POST /api/classify`: disabled by default. Requires explicit activation,
  approval-reference configuration, Access, exact same origin, rate-limit binding
  and an AI binding. Then accepts only `{text, consent:true}`, at most 4,000 UTF-16
  code units / 8 KB text and a 12 KB bounded JSON envelope. Known credential patterns
  are refused; this filter is not comprehensive DLP.

The host applies restrictive CSP, no-store, no-referrer and MIME/frame protections.
It returns no raw exception, request body, JWT, upstream output or source text.
Access uses jose's official remote-JWKS verifier, fixed HTTPS team issuer, RS256,
audience/expiry/not-before/issued-at validation and a 24-hour maximum token age.
The Access application's approved policy decides who receives that audience.

The classifier uses the retrieved Clef typed-choice schema. Only Suno, prompt,
idea and reference are accepted. Output probabilities/usage are validated; uncertain
results remain uncertain. Every response says `applied:false`. Gateway request
logging and caching are disabled per request, with no provider fallback.

## Activation requirements

1. Independently review the exact source/bundle, refresh machine/storage admission
   and qualify the module in the Cloudflare runtime. Node Request/Response tests
   do not establish native Workers behavior.
2. Use the existing account and Access organization. Approve a narrow self-hosted
   app/policy for this companion; configure `ACCESS_TEAM_DOMAIN` and its real
   `ACCESS_AUD`. Do not trust a caller-supplied JWT issuer or use an allow-everyone
   policy. Protect preview hosts and validate a logged-out request too.
3. Upload the exact inspected bundle to the candidate Worker. Keep public routes
   and preview URLs off until the named private-preview activation is approved.
   A version upload is not traffic activation and does not migrate shared storage.
4. Test the actual HTTPS shell, installed service worker, offline draft recovery,
   Android incoming sharing, denied/expired sessions and export on a real phone.
   Access revocation does not erase or encrypt an already-cached local archive.
5. Only after funding/source/limits are approved, add `AI`, an actual
   `INFERENCE_RATE_LIMIT` binding, exact `APP_ORIGIN`, `INFERENCE_APPROVAL_ID` and
   `INFERENCE_ENABLED=true`. A configured approval string is a reference, not a
   human-approval verifier or a hard currency cap. Configure approved spend controls
   separately; rate limits do not bound monthly spending. Start with synthetic
   fixtures before any selected personal text. No automatic corpus ingestion.
6. Configure payload-free operational logs/traces with reviewed query redaction
   and retention before production. No clipboard body or identity belongs in
   telemetry. Observability is a production acceptance item, not enabled by this
   version-upload artifact.

The connected account currently exposes nine Workers, one authenticated gateway
with logs off, and an Access organization with no applications. Its gateway reports
postpaid Workers AI billing. The connection cannot read subscriptions (403).
Startup-credit coverage, balance and inference funding therefore remain unverified;
this implementation does not alter subscriptions, top-ups or spending limits.

## Recovery

Keep the prior Worker version, app/policy IDs and exact bundle hash in the private
release receipt. Code rollback does not roll back account policies or data. This
candidate has no hosted data. Export the plaintext browser archive before device
replacement; trusted device enrollment, encrypted synchronization and independent
key custody still belong to the existing platform's next stage.

Sources retrieved 2026-11-02:
[Access JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/),
[Clef](https://developers.cloudflare.com/workers-ai/models/clef/),
[AI Gateway bindings](https://developers.cloudflare.com/ai-gateway/usage/worker-binding-methods/),
[Worker version upload](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/).

## Staged agent-layer storage (not live)

Nothing below exists in any Cloudflare account. No resource was created, no
Wrangler config was added and nothing deploys or uploads automatically. Clipboard
bodies can hold secrets, so what syncs is the owner's decision, made per item.

- **D1**: `cloud/migrations/0001_clip_mirror.sql` mirrors `shared/clip-item.schema.json`
  (metadata only: clips without `body`, collections, members, tags). It keys on the
  portable `uid`, not the local integer `id`. Not applied.
- **R2** (staged binding `CLIP_BLOBS`): optional home for owner-approved bodies or
  images, only after an explicit per-item opt-in and client-side encryption decision.
- **Vectorize** (staged binding `CLIP_VECTORS`): embeddings of owner-approved previews
  only; never of items with `kind: "secret"`.
- **Workers AI** (staged binding `AI`): inference stays disabled; see the existing
  classification gating above.

Open decisions are listed in the draft PR that introduced this section.
