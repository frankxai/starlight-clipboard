import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

export class CollectorError extends Error {}

export interface Panel {
  port: number;
  token: string;
}

export function clipHome(env: NodeJS.ProcessEnv = process.env): string {
  return env.CLIP_HOME || join(homedir(), ".starlight", "clipboard-index");
}

/** clip.py panel_file(): <CLIP_HOME>/data/panel.json holding {port, token, window_title}. */
export async function readPanel(home: string = clipHome()): Promise<Panel> {
  const file = join(home, "data", "panel.json");
  let raw: string;
  try {
    raw = await readFile(file, "utf8");
  } catch {
    throw new CollectorError(
      `The Starlight Clipboard collector is not running (no panel file at ${file}). Start it with "clips watch" or the Start-menu shortcut.`,
    );
  }
  try {
    const value = JSON.parse(raw) as Partial<Panel>;
    if (!Number.isInteger(value.port) || typeof value.token !== "string" || !value.token) throw new Error("shape");
    return { port: value.port as number, token: value.token };
  } catch {
    throw new CollectorError(`The collector panel file at ${file} is unreadable. Restart the collector.`);
  }
}

export class Collector {
  constructor(private readonly home: string = clipHome()) {}

  async call(method: "GET" | "POST", path: string, params: Record<string, string> = {}, body?: unknown): Promise<unknown> {
    const panel = await readPanel(this.home);
    const url = new URL(`http://127.0.0.1:${panel.port}${path}`);
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    let response: Response;
    try {
      response = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${panel.token}`,
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(12_000),
      });
    } catch {
      throw new CollectorError(
        "The Starlight Clipboard collector is not running or not reachable on 127.0.0.1 (stale panel file). Start it with \"clips watch\".",
      );
    }
    const text = await response.text();
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = undefined;
    }
    if (!response.ok) {
      const detail = parsed && typeof parsed === "object" && "error" in parsed ? String((parsed as { error: unknown }).error) : `HTTP ${response.status}`;
      throw new CollectorError(`Collector rejected the request: ${detail}`);
    }
    if (parsed === undefined) throw new CollectorError("Collector returned a non-JSON response.");
    return parsed;
  }
}
