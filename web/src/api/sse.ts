/** The live stream client: parses server-sent events and reconnects from the last ids seen. */
import type { Message } from "./client";

export interface SseEvent {
  event: string;
  id: string | null;
  data: string;
}

/** Incremental parser for the text/event-stream format. Feed it chunks; it returns whole events. */
export class SseParser {
  private buffer = "";

  feed(chunk: string): SseEvent[] {
    this.buffer += chunk;
    const events: SseEvent[] = [];
    for (;;) {
      const match = /\r\n\r\n|\n\n|\r\r/.exec(this.buffer);
      if (!match) break;
      const block = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const event = parseBlock(block);
      if (event) events.push(event);
    }
    return events;
  }
}

function parseBlock(block: string): SseEvent | null {
  let event = "message";
  let id: string | null = null;
  const data: string[] = [];
  for (const line of block.split(/\r\n|\n|\r/)) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "id") id = value;
    else if (field === "data") data.push(value);
  }
  return data.length === 0 ? null : { event, id, data: data.join("\n") };
}

/** Where the stream stands: the last stored message and the last change event received. */
export interface ResumePoint {
  message: number | null;
  event: number | null;
}

/** Moves a resume point forward from an event id such as `m12` (message) or `e40` (change). */
export function advance(point: ResumePoint, id: string | null): ResumePoint {
  const match = id ? /^([me])(\d+)$/.exec(id) : null;
  if (!match) return point;
  const value = Number(match[2]);
  if (match[1] === "m") return { ...point, message: Math.max(point.message ?? 0, value) };
  return { ...point, event: Math.max(point.event ?? 0, value) };
}

export function streamUrl(projectId: string, point: ResumePoint): string {
  const params = new URLSearchParams();
  if (point.message !== null) params.set("after_message", String(point.message));
  if (point.event !== null) params.set("after_event", String(point.event));
  const query = params.toString();
  return `/stream/v1/projects/${encodeURIComponent(projectId)}${query ? `?${query}` : ""}`;
}

export interface ReplyChunk {
  run_id: string;
  seat: string;
  text: string;
}

export interface ChangeNotice {
  id: number;
  type: string;
  at: string;
}

export interface StreamHandlers {
  onMessage(message: Message): void;
  onChange(change: ChangeNotice): void;
  onReply(chunk: ReplyChunk): void;
  /** Called with true when the stream connects and false when it drops. */
  onStatus(live: boolean): void;
  onSignedOut?(): void;
}

export interface StreamOptions {
  fetchFn?: typeof fetch;
  /** Waits before a reconnect; attempt counts from 1. Replaceable in tests. */
  wait?: (attempt: number) => Promise<void>;
}

const RETRY_STEPS_MS = [1000, 2000, 5000, 10000];

function defaultWait(attempt: number): Promise<void> {
  const delay = RETRY_STEPS_MS[Math.min(attempt - 1, RETRY_STEPS_MS.length - 1)] ?? 10000;
  return new Promise((resolve) => setTimeout(resolve, delay));
}

/** Dispatches one parsed event to the handlers and returns the new resume point. */
export function dispatch(event: SseEvent, point: ResumePoint, handlers: StreamHandlers): ResumePoint {
  let payload: unknown;
  try {
    payload = JSON.parse(event.data);
  } catch {
    return point;
  }
  if (event.event === "message") handlers.onMessage(payload as Message);
  else if (event.event === "change") handlers.onChange(payload as ChangeNotice);
  else if (event.event === "reply") handlers.onReply(payload as ReplyChunk);
  return advance(point, event.id);
}

/**
 * Opens the project stream and keeps it open. On any error it reconnects with the last
 * message and event ids, so nothing is missed or repeated. Returns a function that closes it.
 */
export function openStream(
  projectId: string,
  start: ResumePoint,
  handlers: StreamHandlers,
  options: StreamOptions = {},
): { close(): void; setMessageFloor(id: number): void } {
  const fetchFn = options.fetchFn ?? fetch;
  const wait = options.wait ?? defaultWait;
  const controller = new AbortController();
  let point = start;
  let closed = false;

  async function run(): Promise<void> {
    let attempt = 0;
    while (!closed) {
      try {
        const response = await fetchFn(streamUrl(projectId, point), {
          credentials: "same-origin",
          headers: { accept: "text/event-stream" },
          signal: controller.signal,
        });
        if (response.status === 401) {
          handlers.onSignedOut?.();
          return;
        }
        if (!response.ok || !response.body) throw new Error(`stream answered ${response.status}`);
        attempt = 0;
        handlers.onStatus(true);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const parser = new SseParser();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          for (const event of parser.feed(decoder.decode(value, { stream: true }))) {
            point = dispatch(event, point, handlers);
          }
        }
      } catch {
        // Fall through to reconnect; polling covers the gap meanwhile.
      }
      if (closed) return;
      handlers.onStatus(false);
      attempt += 1;
      await wait(attempt);
    }
  }

  void run();
  return {
    close() {
      closed = true;
      controller.abort();
    },
    setMessageFloor(id: number) {
      point = { ...point, message: Math.max(point.message ?? 0, id) };
    },
  };
}
