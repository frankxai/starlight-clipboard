import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, writeFile, mkdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {packageCandidate, publicAssets, PUBLIC_FILES} from '../cloud/package.mjs';

test('packaging includes only approved source assets and rotates shell cache identity', async () => {
  const a = await publicAssets(); const b = await publicAssets();
  assert.equal(a.release, b.release); assert.equal(Object.keys(a.assets).length, 7);
  assert.match(Buffer.from(a.assets['/sw.js'].base64, 'base64').toString(), new RegExp(`starlight-capture-${a.release}`));
  assert.deepEqual(Object.keys(a.sourceHashes), PUBLIC_FILES);
  assert.equal(Object.hasOwn(a.assets, '/package.json'), false);
});
test('bundled Worker and multipart are inspectable and retain disabled inference', async () => {
  const root = await mkdtemp(join(tmpdir(), 'starlight-cloud-qa-'));
  try {
    const output = join(root, 'candidate');
    const manifest = await packageCandidate(output, {revision: 'a'.repeat(40)});
    const bundle = await readFile(join(output, 'worker.mjs'));
    assert.match(bundle.toString(), /Copyright \(c\) 2018 Filip Skokan/);
    assert.match(bundle.toString(), /THE SOFTWARE IS PROVIDED/);
    assert.equal(createHash('sha256').update(bundle).digest('hex'), manifest.worker_sha256);
    const multipart = await readFile(join(output, 'version-upload.multipart'));
    const parsed = await new Response(multipart, {headers: {'Content-Type': manifest.content_type}}).formData();
    const metadata = JSON.parse(parsed.get('metadata'));
    assert.equal(metadata.main_module, 'worker.mjs');
    assert.equal(metadata.bindings.find(b => b.name === 'INFERENCE_ENABLED').text, 'false');
    assert.equal(metadata.bindings.some(b => ['ai', 'd1', 'kv_namespace', 'r2_bucket'].includes(b.type)), false);
    assert.equal(await parsed.get('worker.mjs').text(), bundle.toString());
    const bundled = await import(pathToFileURL(join(output, 'worker.mjs')).href);
    const r = await bundled.default.fetch(new Request('https://synthetic.test/api/health'), {RELEASE_ID: manifest.release});
    assert.equal((await r.json()).assets_packaged, true);
    assert.equal((await bundled.default.fetch(new Request('https://synthetic.test/'), {})).status, 503);
    await assert.rejects(packageCandidate(output), /EEXIST/);
  } finally { await rm(root, {recursive: true, force: true}); }
});
test('private canaries beside source assets never enter a release and changed assets change identity', async () => {
  const root = await mkdtemp(join(tmpdir(), 'starlight-cloud-assets-'));
  try {
    const mobile = join(root, 'mobile'); await mkdir(mobile);
    for (const name of PUBLIC_FILES) await writeFile(join(mobile, name), await readFile(new URL('../mobile/' + name, import.meta.url)));
    await writeFile(join(mobile, '.env'), 'synthetic-private-canary');
    await writeFile(join(mobile, 'clips.sqlite'), 'synthetic-private-canary');
    const before = await publicAssets(mobile);
    await writeFile(join(mobile, 'style.css'), '/* synthetic updated style */');
    const after = await publicAssets(mobile);
    assert.notEqual(before.release, after.release);
    assert.doesNotMatch(JSON.stringify(after.assets), /synthetic-private-canary/);
    for (const asset of Object.values(after.assets)) {
      assert.doesNotMatch(Buffer.from(asset.base64, 'base64').toString(), /synthetic-private-canary/);
    }
    assert.equal(Object.keys(after.assets).length, 7);
  } finally { await rm(root, {recursive: true, force: true}); }
});
