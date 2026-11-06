import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { createServer as http, type IncomingMessage, type Server } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { Collector } from "../src/client.js";
import { createServer } from "../src/server.js";

const TOKEN = "fake-token";
const seen: { method: string; url: string; auth: string; host: string; body: string }[] = [];
let fake: Server;
let home: string;
let emptyHome: string;

const ITEMS = { device: "pc", devices: ["pc"], items: [
  { id: 3, kind: "secret", preview: "[redacted:token]", body: "[redacted:token]", more: false },
  { id: 2, kind: "text", preview: "two", body: "two", more: false },
  { id: 1, kind: "text", preview: "one", body: "one", more: false },
] };

const read = (req: IncomingMessage) => new Promise<string>((resolve) => {
  let data = ""; req.on("data", (c) => (data += c)); req.on("end", () => resolve(data));
});

before(async () => {
  fake = http(async (req, res) => {
    const body = await read(req);
    seen.push({ method: req.method ?? "", url: req.url ?? "", auth: req.headers.authorization ?? "", host: req.headers.host ?? "", body });
    const send = (code: number, value: unknown) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(value)); };
    if (req.headers.authorization !== `Bearer ${TOKEN}`) return send(404, { error: "no" });
    const url = new URL(req.url ?? "/", "http://x");
    if (url.pathname === "/api/items") return send(200, ITEMS);
    if (url.pathname === "/api/detail" && url.searchParams.get("id") === "307") { res.writeHead(307, { Location: "http://example.invalid/steal" }); return res.end(); }
    if (url.pathname === "/api/detail") return url.searchParams.get("id") === "2" ? send(200, { id: 2, body: "two", state: "active" }) : send(404, { error: "Copy not found." });
    if (url.pathname === "/api/library") return send(200, { collections: [{ id: "midnight-piano" }], tags: [], sync: "local-only", cloud_processing: false });
    if (url.pathname === "/api/add") return send(200, { ok: true, id: 9 });
    if (url.pathname === "/api/copy") return send(200, { ok: true });
    send(404, {});
  });
  await new Promise<void>((r) => fake.listen(0, "127.0.0.1", r));
  const port = (fake.address() as { port: number }).port;
  home = await mkdtemp(join(tmpdir(), "clip-mcp-"));
  emptyHome = await mkdtemp(join(tmpdir(), "clip-mcp-empty-"));
  await mkdir(join(home, "data"));
  await writeFile(join(home, "data", "panel.json"), JSON.stringify({ port, token: TOKEN, window_title: "t" }));
});

after(async () => {
  fake.close();
  await rm(home, { recursive: true, force: true });
  await rm(emptyHome, { recursive: true, force: true });
});

async function connect(dir: string) {
  const server = createServer(new Collector(dir));
  const client = new Client({ name: "test", version: "0" });
  const [a, b] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(a), client.connect(b)]);
  return client;
}

const text = (r: unknown) => ((r as { content: { text: string }[] }).content[0]).text;

test("lists six tools with write annotations on clip_add and clip_copy only", async () => {
  const { tools } = await (await connect(home)).listTools();
  assert.deepEqual(tools.map((t) => t.name).sort(), ["clip_add", "clip_copy", "clip_get", "clip_recent", "clip_search", "library_list"]);
  for (const t of tools) assert.equal(t.annotations?.readOnlyHint, !["clip_add", "clip_copy"].includes(t.name), t.name);
});

test("search uses loopback + bearer token and applies the limit; redacted items pass through unchanged", async () => {
  seen.length = 0;
  const out = JSON.parse(text(await (await connect(home)).callTool({ name: "clip_search", arguments: { query: "use:suno x", limit: 2 } })));
  assert.equal(out.items.length, 2);
  assert.deepEqual(out.items[0], ITEMS.items[0]);
  assert.match(seen[0].url, /^\/api\/items\?q=use%3Asuno\+x$/);
  assert.equal(seen[0].auth, `Bearer ${TOKEN}`);
  assert.match(seen[0].host, /^127\.0\.0\.1:/);
});

test("recent, get, library_list", async () => {
  const c = await connect(home);
  assert.equal(JSON.parse(text(await c.callTool({ name: "clip_recent", arguments: { limit: 1 } }))).items.length, 1);
  assert.equal(JSON.parse(text(await c.callTool({ name: "clip_get", arguments: { id: 2 } }))).body, "two");
  const missing = await c.callTool({ name: "clip_get", arguments: { id: 7 } });
  assert.equal(missing.isError, true);
  assert.match(text(missing), /Copy not found/);
  const lib = JSON.parse(text(await c.callTool({ name: "library_list", arguments: { kind: "collections" } })));
  assert.equal(lib.collections[0].id, "midnight-piano");
  assert.equal(lib.tags, undefined);
});

test("clip_add and clip_copy POST JSON bodies", async () => {
  const c = await connect(home);
  seen.length = 0;
  assert.equal(JSON.parse(text(await c.callTool({ name: "clip_add", arguments: { text: "idea", title: "T" } }))).id, 9);
  assert.deepEqual(JSON.parse(seen[0].body), { text: "# T\n\nidea" });
  assert.equal(JSON.parse(text(await c.callTool({ name: "clip_copy", arguments: { id: 2 } }))).ok, true);
  assert.equal(seen[1].method, "POST");
  assert.deepEqual(JSON.parse(seen[1].body), { id: 2 });
});

test("clear error when the collector is not running", async () => {
  const r = await (await connect(emptyHome)).callTool({ name: "clip_recent", arguments: {} });
  assert.equal(r.isError, true);
  assert.match(text(r), /collector is not running/);
});

test("clear error when panel file is stale (nothing listening)", async () => {
  const stale = await mkdtemp(join(tmpdir(), "clip-mcp-stale-"));
  await mkdir(join(stale, "data"));
  await writeFile(join(stale, "data", "panel.json"), JSON.stringify({ port: 1, token: "x" }));
  const r = await (await connect(stale)).callTool({ name: "clip_recent", arguments: {} });
  assert.equal(r.isError, true);
  assert.match(text(r), /not running or not reachable/);
  await rm(stale, { recursive: true, force: true });
});

test("redirects from the collector port are refused, not followed", async () => {
  const r = await (await connect(home)).callTool({ name: "clip_get", arguments: { id: 307 } });
  assert.equal(r.isError, true);
  assert.match(text(r), /not running or not reachable/);
});
