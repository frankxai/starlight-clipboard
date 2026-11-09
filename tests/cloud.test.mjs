import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {createWorker} from '../cloud/worker.mjs';
import {boundedJson, decision, selection, MODEL, GATEWAY} from '../cloud/classify.mjs';
const require = createRequire(new URL('../cloud/package.json', import.meta.url));
const {generateKeyPair, exportJWK, SignJWT} = await import(pathToFileURL(require.resolve('jose')));
const keys = await generateKeyPair('RS256');
const jwk = {...await exportJWK(keys.publicKey), kid: 'qa-key', alg: 'RS256', use: 'sig'};
const issuer = 'https://synthetic-team.cloudflareaccess.com', audience = 'a'.repeat(64);
const base = 'https://capture.example.test';
const assets = {'/index.html': {type: 'text/html', base64: Buffer.from('<h1>Synthetic Starlight</h1>').toString('base64')},
  '/sw.js': {type: 'text/javascript', base64: Buffer.from('// synthetic worker').toString('base64')}};
const seen = [];
const worker = createWorker(assets, async url => {
  seen.push(String(url));
  assert.equal(String(url), issuer + '/cdn-cgi/access/certs');
  return Response.json({keys: [jwk]});
});
const env = {ACCESS_TEAM_DOMAIN: issuer, ACCESS_AUD: audience, APP_ORIGIN: base, RELEASE_ID: 'synthetic'};
async function token(overrides = {}, header = {}) {
  const now = Math.floor(Date.now()/1000);
  return new SignJWT({iss: issuer, aud: audience, sub: 'synthetic-device-user', type: 'app', iat: now, exp: now+120, ...overrides})
    .setProtectedHeader({alg: 'RS256', kid: 'qa-key', ...header}).sign(keys.privateKey);
}
const headers = jwt => ({'Cf-Access-Jwt-Assertion': jwt, Origin: base, 'Content-Type': 'application/json'});
const good = () => ({model: 'clef', answers: {use_case: {type: 'choice', choice: 'suno', confidence: 0.91,
  probabilities: {suno: 0.91, prompt: 0.03, idea: 0.03, reference: 0.03}}}, usage: {input_tokens: 78, output_tokens: 0}});
const request = (path, options) => new Request(base + path, options);

test('health is payload-free and cannot imply cloud sync or activation', async () => {
  const r = await worker.fetch(request('/api/health'), env);
  const body = await r.json();
  assert.equal(r.status, 200); assert.equal(body.automatic_uploads, false);
  assert.equal(body.account_sync, 'not-implemented'); assert.equal(body.inference_enabled, false);
  assert.equal(body.assets_packaged, true); assert.equal(r.headers.get('Cache-Control'), 'no-store');
  const notReady = await worker.fetch(request('/api/health'), {...env, INFERENCE_ENABLED: 'true'});
  assert.equal((await notReady.json()).inference_enabled, false);
  assert.equal(r.headers.get('Access-Control-Allow-Origin'), null);
  assert.equal((await worker.fetch(request('/api/health', {method: 'HEAD'}), env)).body, null);
});
test('static app refuses missing configuration and missing credentials', async () => {
  assert.equal((await worker.fetch(request('/'), {})).status, 503);
  assert.equal((await worker.fetch(request('/'), env)).status, 401);
  assert.equal((await worker.fetch(request('/.env'), env)).status, 404);
  assert.equal((await worker.fetch(request('/data/clips.sqlite'), env)).status, 404);
});
test('real RSA verification serves assets with CSP and worker scope', async () => {
  const jwt = await token();
  const r = await worker.fetch(request('/', {headers: headers(jwt)}), env);
  assert.equal(r.status, 200); assert.match(await r.text(), /Synthetic Starlight/);
  assert.match(r.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/);
  assert.equal(r.headers.get('Referrer-Policy'), 'no-referrer');
  const sw = await worker.fetch(request('/sw.js', {headers: headers(jwt), method: 'HEAD'}), env);
  assert.equal(sw.headers.get('Service-Worker-Allowed'), '/'); assert.equal(sw.body, null);
});
test('wrong audience, issuer, expiry, future activation and service identities fail closed', async () => {
  const now = Math.floor(Date.now()/1000);
  for (const override of [{aud: 'b'.repeat(64)}, {iss: 'https://evil.test'}, {exp: now-60},
    {nbf: now+120}, {iat: now+120}, {type: 'service'}, {sub: ''}]) {
    const jwt = await token(override);
    const r = await worker.fetch(request('/', {headers: headers(jwt)}), env);
    assert.equal(r.status, 401, JSON.stringify(override));
    assert.equal((await r.json()).error, 'access_invalid');
  }
});
test('untrusted JWT key URLs never choose the JWKS destination', async () => {
  seen.length = 0;
  const r = await worker.fetch(request('/', {headers: headers(await token({}, {jku: 'https://evil.test/keys'}))}), env);
  assert.equal(r.status, 200);
  assert.deepEqual(seen, [issuer + '/cdn-cgi/access/certs']);
});
test('tampered signatures, oversized tokens and arbitrary issuer configuration are refused', async () => {
  const jwt = await token();
  const pieces = jwt.split('.'); pieces[1] = Buffer.from('{"sub":"forged"}').toString('base64url');
  assert.equal((await worker.fetch(request('/', {headers: headers(pieces.join('.'))}), env)).status, 401);
  assert.equal((await worker.fetch(request('/', {headers: headers('a'.repeat(8193))}), env)).status, 401);
  assert.equal((await worker.fetch(request('/', {headers: headers(jwt)}), {...env, ACCESS_TEAM_DOMAIN: 'https://evil.test'})).status, 503);
});
test('a host share POST never reads, forwards or reflects the private body', async () => {
  const body = 'private-synthetic-canary';
  const req = request('/share', {method: 'POST', body});
  const r = await worker.fetch(req, env);
  assert.equal(r.status, 428); assert.equal(req.bodyUsed, false);
  assert.doesNotMatch(await r.text(), new RegExp(body));
  assert.equal(r.headers.get('Location'), null);
});
test('inference is disabled without all activation prerequisites and never consumes the body', async () => {
  for (const extra of [{}, {INFERENCE_ENABLED: 'true'}, {INFERENCE_ENABLED: true}]) {
    const req = request('/api/classify', {method: 'POST', body: 'private canary'});
    const r = await worker.fetch(req, {...env, ...extra});
    assert.equal(r.status, 503); assert.equal(req.bodyUsed, false);
  }
});
test('an approved synthetic request exercises Access, rate limit, typed model and private gateway options', async () => {
  const calls = [];
  const activated = {...env, INFERENCE_ENABLED: 'true', INFERENCE_APPROVAL_ID: 'synthetic-only',
    INFERENCE_RATE_LIMIT: {async limit(input) {calls.push(input); return {success: true};}},
    AI: {async run(...args) {calls.push(args); return good();}}};
  const r = await worker.fetch(request('/api/classify', {method: 'POST', headers: headers(await token()),
    body: JSON.stringify({text: 'Intimate felt piano, 84 BPM.', consent: true})}), activated);
  assert.equal(r.status, 200); const result = await r.json();
  assert.equal(result.applied, false); assert.equal(result.use_case, 'suno');
  assert.equal(calls.length, 2); assert.equal(calls[0].key, 'synthetic-device-user');
  assert.equal(calls[1][0], MODEL); assert.equal(calls[1][1].model, 'clef');
  assert.deepEqual(calls[1][2], {gateway: {id: GATEWAY, skipCache: true, collectLog: false}});
  assert.equal(Object.hasOwn(result, 'text'), false);
});
test('cross-origin and rate-denied requests cannot call the model or read their body', async () => {
  let modelCalls = 0;
  const activated = {...env, INFERENCE_ENABLED: 'true', INFERENCE_APPROVAL_ID: 'synthetic-only',
    INFERENCE_RATE_LIMIT: {async limit() {return {success: false};}}, AI: {async run() {modelCalls++; return good();}}};
  const jwt = await token();
  for (const [origin, code] of [['https://evil.test', 403], [base, 429]]) {
    const req = request('/api/classify', {method: 'POST', headers: {...headers(jwt), Origin: origin}, body: 'private'});
    assert.equal((await worker.fetch(req, activated)).status, code); assert.equal(req.bodyUsed, false);
  }
  assert.equal(modelCalls, 0);
});
test('explicit consent, exact input shape, bounds and credential refusal precede inference', () => {
  for (const input of [{text: 'x'}, {text: 'x', consent: false}, {text: 'x', consent: true, model: 'anything'},
    {text: ' ', consent: true}, {text: 'x'.repeat(4001), consent: true},
    {text: 'password=synthetic-canary', consent: true}]) assert.throws(() => selection(input));
  assert.equal(selection({text: 'Original thought', consent: true}), 'Original thought');
});
test('stream size and invalid UTF8/JSON fail without silently truncating', async () => {
  await assert.rejects(boundedJson(request('/x', {method: 'POST', headers: {'content-type': 'application/json'}, body: 'x'.repeat(12001)})), /selection_too_large/);
  await assert.rejects(boundedJson(request('/x', {method: 'POST', headers: {'content-type': 'application/json'}, body: new Uint8Array([255])})), /invalid_json/);
  await assert.rejects(boundedJson(request('/x', {method: 'POST', headers: {'content-type': 'text/plain'}, body: '{}'})), /json_required/);
});
test('a stalled body times out and its reader is cancelled', async () => {
  let cancelled = false;
  const body = new ReadableStream({start(controller) {controller.enqueue(new TextEncoder().encode('{'));},
    cancel() {cancelled = true;}});
  const req = request('/x', {method: 'POST', duplex: 'half', headers: {'content-type': 'application/json'}, body});
  await assert.rejects(boundedJson(req), /selection_timeout/);
  assert.equal(cancelled, true);
});
test('upstream errors never expose selections or provider exception bodies', async () => {
  const r = await worker.fetch(request('/api/classify', {method: 'POST', headers: headers(await token()),
    body: JSON.stringify({text: 'Synthetic original', consent: true})}), {...env,
    INFERENCE_ENABLED: 'true', INFERENCE_APPROVAL_ID: 'synthetic-only',
    INFERENCE_RATE_LIMIT: {async limit() {return {success: true};}},
    AI: {async run() {throw Error('private-synthetic-provider-canary');}}});
  assert.equal(r.status, 502); assert.doesNotMatch(await r.text(), /private-synthetic|Synthetic original/);
});
test('uncertain or malformed model results cannot become an applied classification', () => {
  const uncertain = good(); uncertain.answers.use_case.confidence = 0.6;
  assert.equal(decision(uncertain).use_case, 'uncertain');
  for (const mutate of [r => r.answers.use_case.probabilities.idea = NaN,
    r => r.answers.use_case.choice = 'execute-shell', r => r.answers.use_case.probabilities.other = 0,
    r => r.answers.use_case.probabilities.suno = 0, r => r.model = 'other', r => delete r.usage]) {
    const r = good(); mutate(r); assert.throws(() => decision(r));
  }
});
