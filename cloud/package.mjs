import {readFile, writeFile, mkdir, lstat, realpath} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {resolve, dirname, join, relative, isAbsolute} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {build} from 'esbuild';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..');
const require = createRequire(import.meta.url);
export const PUBLIC_FILES = Object.freeze(['index.html', 'style.css', 'app.js', 'store.js', 'sw.js', 'manifest.webmanifest', 'icon.png']);
const TYPES = {'html': 'text/html; charset=utf-8', 'css': 'text/css; charset=utf-8', 'js': 'text/javascript; charset=utf-8', 'webmanifest': 'application/manifest+json', 'png': 'image/png'};
const sha = input => createHash('sha256').update(input).digest('hex');

export async function publicAssets(mobileRoot = join(REPO, 'mobile')) {
  const root = await realpath(mobileRoot);
  const files = {};
  for (const name of PUBLIC_FILES) {
    const path = join(root, name);
    const stat = await lstat(path);
    const target = await realpath(path);
    const rel = relative(root, target);
    if (!stat.isFile() || stat.isSymbolicLink() || isAbsolute(rel) || rel.startsWith('..')) throw Error('Public asset escaped its source');
    const bytes = await readFile(path);
    if (bytes.length > 500000) throw Error('Public asset exceeds packaging limit');
    files[name] = bytes;
  }
  const sourceHashes = Object.fromEntries(PUBLIC_FILES.map(name => [name, sha(files[name])]));
  const release = sha(JSON.stringify(sourceHashes)).slice(0, 20);
  const sw = files['sw.js'].toString('utf8');
  if (!sw.includes('const CACHE="starlight-capture-v1";')) throw Error('Review the changed service-worker release contract');
  files['sw.js'] = Buffer.from(sw.replace('const CACHE="starlight-capture-v1";', `const CACHE="starlight-capture-${release}";`));
  const assets = Object.fromEntries(PUBLIC_FILES.map(name => ['/' + name, {
    type: TYPES[name.split('.').at(-1)], base64: files[name].toString('base64'),
  }]));
  return {assets, release, sourceHashes};
}

export async function packageCandidate(output, {mobileRoot, revision = 'working-tree'} = {}) {
  if (!output || !isAbsolute(output)) throw Error('Use an explicit absolute private output path');
  const destination = resolve(output);
  const fromRepo = relative(REPO, destination);
  if (!fromRepo.startsWith('..') && !isAbsolute(fromRepo)) throw Error('Package outside the source checkout');
  // A fresh leaf prevents overwriting another release or following an existing symlink.
  await mkdir(destination, {recursive: false});
  const packet = await publicAssets(mobileRoot);
  const bundled = await build({entryPoints: [join(HERE, 'worker.mjs')], bundle: true, write: false,
    platform: 'browser', format: 'esm', target: 'es2022', legalComments: 'inline', minify: false,
    plugins: [{name: 'public-assets-only', setup(api) {
      api.onLoad({filter: /[\\/]assets\.mjs$/}, () => ({contents: `export const PUBLIC_ASSETS = ${JSON.stringify(packet.assets)};`, loader: 'js'}));
    }}],
  });
  const joseRoot = resolve(dirname(require.resolve('jose')), '..', '..');
  const license = await readFile(join(joseRoot, 'LICENSE.md'), 'utf8');
  const notices = `jose 6.2.15\n${license}`;
  const module = Buffer.concat([Buffer.from(bundled.outputFiles[0].contents), Buffer.from(`\n/*! Third-party notice\n${notices}\n*/\n`)]);
  const bindings = [
    {name: 'RELEASE_ID', type: 'plain_text', text: packet.release},
    {name: 'INFERENCE_ENABLED', type: 'plain_text', text: 'false'},
  ];
  const metadata = {main_module: 'worker.mjs', compatibility_date: '2026-11-02', bindings,
    annotations: {'workers/message': 'Starlight private mobile candidate; inference disabled',
      ...( /^[a-f0-9]{40}$/.test(revision) ? {'workers/commit_sha': revision} : {})}};
  const boundary = `starlight-${sha(module).slice(0, 28)}`;
  const head = `--${boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(metadata)}\r\n--${boundary}\r\nContent-Disposition: form-data; name="worker.mjs"; filename="worker.mjs"\r\nContent-Type: application/javascript+module\r\n\r\n`;
  const upload = Buffer.concat([Buffer.from(head), module, Buffer.from(`\r\n--${boundary}--\r\n`)]);
  await writeFile(join(destination, 'worker.mjs'), module, {flag: 'wx'});
  await writeFile(join(destination, 'version-upload.multipart'), upload, {flag: 'wx'});
  await writeFile(join(destination, 'metadata.json'), JSON.stringify(metadata, null, 2) + '\n', {flag: 'wx'});
  await writeFile(join(destination, 'THIRD-PARTY-NOTICES.txt'), notices, {flag: 'wx'});
  const manifest = {author: 'Codex', created_at: new Date().toISOString(), revision: 1, source_revision: revision,
    review_state: 'built-not-deployed', release: packet.release, source_assets: packet.sourceHashes,
    generated_worker_cache: `starlight-capture-${packet.release}`,
    worker_sha256: sha(module), upload_sha256: sha(upload), content_type: `multipart/form-data; boundary=${boundary}`,
    bytes: module.length, public_files: PUBLIC_FILES, inference_enabled: false, account_sync: false,
    permissions_missing: ['Access audience and approved policy', 'named activation/release approval'],
    deployment: 'POST /accounts/{account_id}/workers/scripts/starlight-clipboard-companion/versions; no traffic deployment included'};
  await writeFile(join(destination, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', {flag: 'wx'});
  return manifest;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { console.log(JSON.stringify(await packageCandidate(process.argv[2], {revision: process.argv[3]}))); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
