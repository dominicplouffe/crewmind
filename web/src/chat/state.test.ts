import { describe, expect, it } from "vitest";
import type { Message } from "../api/client";
import { initialState, reduce, type ChatState } from "./state";

function message(id: number, extra: Partial<Message> = {}): Message {
  return {
    id, channel: "project chat", author_kind: "person", author: "Admin", kind: "message", body: `m${id}`,
    reply_to: null, thread_id: null, run_id: null, detail: null, at: "2026-01-01T00:00:00Z", ...extra,
  };
}

describe("chat state", () => {
  it("keeps messages in order without duplicates, whichever way they arrive", () => {
    let state: ChatState = reduce(initialState, { type: "messages", items: [message(2), message(1)], loaded: true });
    state = reduce(state, { type: "messages", items: [message(2, { body: "again" }), message(3)] });
    expect(state.messages.map((m) => [m.id, m.body])).toEqual([[1, "m1"], [2, "again"], [3, "m3"]]);
  });

  it("builds a typing bubble from reply chunks and removes it when the stored message arrives", () => {
    let state = reduce(initialState, { type: "reply", chunk: { run_id: "r1", seat: "CEO", text: "Here " }, at: 1 });
    state = reduce(state, { type: "reply", chunk: { run_id: "r1", seat: "CEO", text: "is" }, at: 2 });
    expect(state.typing).toEqual([{ runId: "r1", seat: "CEO", text: "Here is", updatedAt: 2 }]);
    state = reduce(state, { type: "messages", items: [message(5, { author_kind: "agent", author: "CEO", run_id: "r1" })] });
    expect(state.typing).toEqual([]);
  });

  it("marks a sent message as delivered and drops the pending copy", () => {
    let state = reduce(initialState, { type: "pending", pending: { key: "k", body: "hi", replyTo: null, error: null } });
    state = reduce(state, { type: "delivered", key: "k", message: message(7) });
    expect(state.pending).toEqual([]);
    expect(state.messages.map((m) => m.id)).toEqual([7]);
  });

  it("keeps a failed message with the server's words so it can be retried", () => {
    let state = reduce(initialState, { type: "pending", pending: { key: "k", body: "hi", replyTo: null, error: null } });
    state = reduce(state, { type: "sendFailed", key: "k", message: "The project is stopped.", hint: "Start a new one." });
    expect(state.pending[0]?.error).toEqual({ message: "The project is stopped.", hint: "Start a new one." });
  });

  it("puts an earlier page above what is shown and remembers where the page before it starts", () => {
    let state = reduce(initialState, { type: "history", items: [message(51), message(52)], earlier: 51 });
    expect(state.loaded).toBe(true);
    expect(state.earlier).toBe(51);
    state = reduce(state, { type: "messages", items: [message(53)] });
    expect(state.earlier).toBe(51);
    state = reduce(state, { type: "history", items: [message(49), message(50), message(51)], earlier: null });
    expect(state.messages.map((m) => m.id)).toEqual([49, 50, 51, 52, 53]);
    expect(state.earlier).toBeNull();
  });

  it("keeps orders, reopen requests and example marks by id", () => {
    const order = { id: 2, text: "Use metric units.", state: "proposed", proposed_by: "CEO", being_shortened: false };
    let state = reduce(initialState, { type: "listening", orders: [order], requests: [] });
    state = reduce(state, { type: "order", order: { ...order, state: "active" } });
    expect(state.orders[2]?.state).toBe("active");
    state = reduce(state, { type: "example", messageId: 7, marked: true });
    state = reduce(state, { type: "example", messageId: 7, marked: false });
    expect(state.examples).toEqual({ 7: false });
  });
});

it("drops late words of a reply the person stopped (CHAT-4)", () => {
  const chunk = { run_id: "r1", seat: "CEO", text: "word " };
  let state = reduce(initialState, { type: "reply", chunk, at: 1 });
  expect(state.typing).toHaveLength(1);
  state = reduce(state, { type: "dropTyping", runId: "r1" });
  state = reduce(state, { type: "reply", chunk, at: 2 });
  expect(state.typing).toHaveLength(0);
  state = reduce(state, { type: "reply", chunk: { ...chunk, run_id: "r2" }, at: 3 });
  expect(state.typing).toHaveLength(1);
});

it("says the stream dropped only once it reported a failure, not while it first connects", () => {
  expect(initialState.dropped).toBe(false);
  const connected = reduce(initialState, { type: "live", live: true });
  expect([connected.live, connected.dropped]).toEqual([true, false]);
  const lost = reduce(connected, { type: "live", live: false });
  expect([lost.live, lost.dropped]).toEqual([false, true]);
  // A stream that never connects reports a failure too.
  expect(reduce(initialState, { type: "live", live: false }).dropped).toBe(true);
});
