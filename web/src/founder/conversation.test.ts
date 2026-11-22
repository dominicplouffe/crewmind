import { describe, expect, it } from "vitest";
import {
  actionOf,
  draftingStreamUrl,
  initialConversation,
  lastLineId,
  reduceConversation,
  type ConversationAction,
  type ConversationState,
} from "./conversation";
import type { Drafting, Line } from "./logic";

const line = (id: number, author = "founder", detail: Line["detail"] = null): Line => ({
  id,
  author,
  body: `line ${id}`,
  detail,
  at: "2030-01-07T09:00:00Z",
});

function view(lines: Line[], extra: Partial<Drafting> = {}): Drafting {
  return {
    drafting_id: "d1",
    state: "drafting",
    quick: false,
    waiting_for: "the Founder",
    failure: null,
    lines,
    questions: [],
    ledger: [],
    draft: null,
    grade: null,
    rehearsal: null,
    ready: false,
    not_ready_because: [],
    rules_hit: [],
    project_id: null,
    ...extra,
  };
}

function play(actions: ConversationAction[], from: ConversationState = initialConversation): ConversationState {
  return actions.reduce(reduceConversation, from);
}

const ids = (state: ConversationState): number[] => state.view?.lines.map((item) => item.id) ?? [];

describe("reduceConversation (FND-1)", () => {
  it("adds the Founder's words as they arrive, and drops them when the finished line is stored", () => {
    const writing = play([
      { type: "view", view: view([line(1, "person")]) },
      { type: "reply", text: "Who " },
      { type: "reply", text: "is it for?" },
    ]);
    expect(writing.reply).toBe("Who is it for?");
    const stored = reduceConversation(writing, { type: "line", line: line(3) });
    expect(stored.reply).toBe("");
    expect(ids(stored)).toEqual([1, 3]);
  });

  it("keeps the words while only a question's line has arrived, because the Founder is still writing", () => {
    const state = play([
      { type: "view", view: view([line(1, "person")]) },
      { type: "reply", text: "Here is " },
      { type: "line", line: line(2, "founder", { kind: "question", id: 7 }) },
    ]);
    expect(state.reply).toBe("Here is ");
    expect(ids(state)).toEqual([1, 2]);
  });

  it("stores a line once, in order, however it arrives", () => {
    const state = play([
      { type: "view", view: view([line(1, "person"), line(2)]) },
      { type: "line", line: line(4, "person") },
      { type: "line", line: line(2) },
      { type: "line", line: line(3) },
    ]);
    expect(ids(state)).toEqual([1, 2, 3, 4]);
  });

  it("ignores a line before the conversation is loaded", () => {
    expect(reduceConversation(initialConversation, { type: "line", line: line(1) })).toBe(initialConversation);
  });

  it("keeps lines the stream added when an older reload arrives after them", () => {
    const state = play([
      { type: "view", view: view([line(1, "person")]) },
      { type: "line", line: line(2) },
      { type: "view", view: view([line(1, "person")], { waiting_for: "you" }) },
    ]);
    expect(ids(state)).toEqual([1, 2]);
    expect(state.view?.waiting_for).toBe("you");
  });

  it("does not carry lines over from another conversation", () => {
    const state = play([
      { type: "view", view: view([line(1, "person"), line(9)]) },
      { type: "view", view: view([line(3, "person")], { drafting_id: "d2" }) },
    ]);
    expect(ids(state)).toEqual([3]);
  });

  it("clears unfinished words once the Founder no longer owes a turn", () => {
    const writing = play([{ type: "view", view: view([]) }, { type: "reply", text: "Half a sen" }]);
    expect(reduceConversation(writing, { type: "view", view: view([]) }).reply).toBe("Half a sen");
    expect(reduceConversation(writing, { type: "view", view: view([], { waiting_for: "you" }) }).reply).toBe("");
  });

  it("counts each change the stream reports, and remembers that the stream dropped", () => {
    const state = play([{ type: "live", live: true }, { type: "changed" }, { type: "changed" }]);
    expect(state).toMatchObject({ live: true, dropped: false, stale: 2 });
    const down = reduceConversation(state, { type: "live", live: false });
    expect(down).toMatchObject({ live: false, dropped: true });
    expect(reduceConversation(down, { type: "live", live: true })).toMatchObject({ live: true, dropped: true });
  });

  it("starts again on reset", () => {
    expect(play([{ type: "view", view: view([line(1)]) }, { type: "reset" }])).toBe(initialConversation);
  });
});

describe("actionOf", () => {
  const event = (name: string, data: unknown): { event: string; id: string | null; data: string } => ({
    event: name,
    id: null,
    data: typeof data === "string" ? data : JSON.stringify(data),
  });

  it("reads a stored line, the Founder's words, and a change", () => {
    expect(actionOf(event("line", line(5)))).toEqual({ type: "line", line: line(5) });
    expect(actionOf(event("reply", { text: "Who " }))).toEqual({ type: "reply", text: "Who " });
    expect(actionOf(event("state", { state: "created" }))).toEqual({ type: "changed" });
  });

  it("ignores what it cannot read", () => {
    expect(actionOf(event("line", "not json"))).toBeNull();
    expect(actionOf(event("line", { body: "no id" }))).toBeNull();
    expect(actionOf(event("reply", { text: 4 }))).toBeNull();
    expect(actionOf(event("other", {}))).toBeNull();
    expect(actionOf(event("state", "null"))).toBeNull();
  });
});

describe("resuming the stream", () => {
  it("asks for the lines after the last one held", () => {
    expect(lastLineId(null)).toBe(0);
    expect(lastLineId(view([line(3), line(8), line(5)]))).toBe(8);
    expect(draftingStreamUrl("d 1", 8)).toBe("/stream/v1/draftings/d%201?after_line=8");
  });
});
