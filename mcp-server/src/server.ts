import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { Collector, CollectorError } from "./client.js";

type Result = { content: { type: "text"; text: string }[]; isError?: boolean };

const ok = (value: unknown): Result => ({ content: [{ type: "text", text: JSON.stringify(value, null, 2) }] });
const fail = (error: unknown): Result => ({
  content: [{ type: "text", text: error instanceof CollectorError ? error.message : "Unexpected error talking to the collector." }],
  isError: true,
});

async function guard(run: () => Promise<unknown>): Promise<Result> {
  try {
    return ok(await run());
  } catch (error) {
    return fail(error);
  }
}

interface ItemsResponse {
  items: unknown[];
  [key: string]: unknown;
}

const limitSchema = z.number().int().min(1).max(200);

export function createServer(collector: Collector = new Collector()): McpServer {
  const server = new McpServer({ name: "starlight-clipboard", version: "0.1.0" });
  const readOnly = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };

  // /api/items has no limit parameter; the limit is applied here. Items are passed through as returned.
  const items = async (query: string, limit: number) => {
    const response = (await collector.call("GET", "/api/items", { q: query })) as ItemsResponse;
    return { ...response, items: response.items.slice(0, limit) };
  };

  server.registerTool(
    "clip_search",
    { description: "Full-text search of the local clipboard archive (GET /api/items). Supports filters such as use:suno, state:any, app:chrome.",
      inputSchema: { query: z.string().min(1), limit: limitSchema.default(20) }, annotations: { title: "Search clips", ...readOnly } },
    ({ query, limit }) => guard(() => items(query, limit)),
  );
  server.registerTool(
    "clip_recent",
    { description: "Newest clips (GET /api/items with an empty query).",
      inputSchema: { limit: limitSchema.default(20) }, annotations: { title: "Recent clips", ...readOnly } },
    ({ limit }) => guard(() => items("", limit)),
  );
  server.registerTool(
    "clip_get",
    { description: "Full retained body and state of one clip (GET /api/detail).",
      inputSchema: { id: z.number().int().min(1) }, annotations: { title: "Get clip", ...readOnly } },
    ({ id }) => guard(() => collector.call("GET", "/api/detail", { id: String(id) })),
  );
  server.registerTool(
    "library_list",
    { description: "Private library (GET /api/library): 'collections' (combos), 'tags' (empty without a clip) or 'all'.",
      inputSchema: { kind: z.enum(["all", "collections", "tags"]).default("all") }, annotations: { title: "List library", ...readOnly } },
    ({ kind }) => guard(async () => {
      const library = (await collector.call("GET", "/api/library")) as Record<string, unknown>;
      if (kind === "all") return library;
      return { [kind]: library[kind], sync: library.sync, cloud_processing: library.cloud_processing };
    }),
  );
  server.registerTool(
    "clip_add",
    { description: "WRITE: save an idea to the archive as a saved clip (POST /api/add). The collector has no title field, so a title is stored as a first line '# <title>'. Does not touch the system clipboard.",
      inputSchema: { text: z.string().min(1).max(100_000), title: z.string().max(200).optional() },
      annotations: { title: "Add clip", readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false } },
    ({ text, title }) => guard(() => collector.call("POST", "/api/add", {}, { text: title ? `# ${title}\n\n${text}` : text })),
  );
  server.registerTool(
    "clip_copy",
    { description: "WRITE: put a stored clip on the Windows system clipboard (POST /api/copy). Overwrites whatever is currently copied.",
      inputSchema: { id: z.number().int().min(1) },
      annotations: { title: "Copy clip to clipboard", readOnlyHint: false, destructiveHint: true, idempotentHint: true, openWorldHint: false } },
    ({ id }) => guard(() => collector.call("POST", "/api/copy", {}, { id })),
  );
  return server;
}
