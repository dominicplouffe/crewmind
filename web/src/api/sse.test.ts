import { describe, expect, it, vi } from "vitest";
import { SseParser, advance, dispatch, openStream, streamUrl, type ResumePoint, type StreamHandlers } from "./sse";

function handlers(): StreamHandlers & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    onMessage: (message) => calls.push(`message:${message.id}`),
    onChange: (change) => calls.push(`change:${change.type}`),
    onReply: (chunk) => calls.push(`reply:${chunk.text}`),
    onStatus: (live) => calls.push(`live:${live}`),
  };
}

describe("SseParser", () => {
  it("parses events with names, ids and data", () => {
    const parser = new SseParser();
    const events = parser.feed('event: change\nid: e6\ndata: {"id": 6}\n\nevent: reply\ndata: {"text": "Hi "}\n\n');
    expect(events).toEqual([
      { event: "change", id: "e6", data: '{"id": 6}' },
      { event: "reply", id: null, data: '{"text": "Hi "}' },
    ]);
  });

  it("joins an event that arrives split across chunks", () => {
    const parser = new SseParser();
    expect(parser.feed("event: mess")).toEqual([]);
    expect(parser.feed('age\nid: m3\ndata: {"id"')).toEqual([]);
    expect(parser.feed(": 3}\n\n")).toEqual([{ event: "message", id: "m3", data: '{"id": 3}' }]);
  });

  it("handles CRLF line ends, comments and multi-line data", () => {
    const parser = new SseParser();
    const events = parser.feed(": keep-alive\r\n\r\ndata: one\r\ndata: two\r\n\r\n");
    expect(events).toEqual([{ event: "message", id: null, data: "one\ntwo" }]);
  });
});

describe("resume ids", () => {
  it("tracks the last message and change ids separately", () => {
    let point: ResumePoint = { message: 4, event: null };
    point = advance(point, "m7");
    point = advance(point, "e40");
    point = advance(point, "m5");
    point = advance(point, null);
    point = advance(point, "x9");
    expect(point).toEqual({ message: 7, event: 40 });
  });

  it("builds the stream address from the resume point", () => {
    expect(streamUrl("p1", { message: null, event: null })).toBe("/stream/v1/projects/p1");
    expect(streamUrl("p1", { message: 7, event: 40 })).toBe("/stream/v1/projects/p1?after_message=7&after_event=40");
  });

  it("dispatches by event name and ignores data that is not JSON", () => {
    const h = handlers();
    let point: ResumePoint = { message: null, event: null };
    point = dispatch({ event: "message", id: "m2", data: '{"id": 2}' }, point, h);
    point = dispatch({ event: "change", id: "e9", data: '{"id": 9, "type": "run.state_changed", "at": ""}' }, point, h);
    point = dispatch({ event: "reply", id: null, data: '{"run_id": "r", "seat": "CEO", "text": "Hi"}' }, point, h);
    point = dispatch({ event: "message", id: "m3", data: "not json" }, point, h);
    expect(h.calls).toEqual(["message:2", "change:run.state_changed", "reply:Hi"]);
    expect(point).toEqual({ message: 2, event: 9 });
  });
});

describe("openStream", () => {
  function body(text: string): Response {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    });
    return new Response(stream, { status: 200 });
  }

  it("reconnects after the stream ends, asking only for what came after the last ids", async () => {
    const h = handlers();
    const urls: string[] = [];
    let release: () => void = () => {};
    const finished = new Promise<void>((resolve) => (release = resolve));
    const fetchFn = vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      if (urls.length === 1) return body('event: message\nid: m5\ndata: {"id": 5}\n\nevent: change\nid: e12\ndata: {"id": 12, "type": "t", "at": ""}\n\n');
      if (urls.length === 2) throw new Error("network down");
      release();
      return new Promise<Response>(() => {});
    });
    const stream = openStream("p1", { message: 4, event: null }, h, { fetchFn: fetchFn as typeof fetch, wait: async () => {} });
    await finished;
    stream.close();
    expect(urls).toEqual([
      "/stream/v1/projects/p1?after_message=4",
      "/stream/v1/projects/p1?after_message=5&after_event=12",
      "/stream/v1/projects/p1?after_message=5&after_event=12",
    ]);
    expect(h.calls).toEqual(["live:true", "message:5", "change:t", "live:false", "live:false"]);
  });

  it("stops and reports when the session has ended", async () => {
    const signedOut = vi.fn();
    const fetchFn = vi.fn(async () => new Response("{}", { status: 401 }));
    openStream("p1", { message: null, event: null }, { ...handlers(), onSignedOut: signedOut }, { fetchFn: fetchFn as typeof fetch, wait: async () => {} });
    await vi.waitFor(() => expect(signedOut).toHaveBeenCalledTimes(1));
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });
});
