import { describe, expect, it } from "vitest";
import {
  AWAY_SECTIONS,
  asksFirst,
  canExtend,
  deadlineText,
  decideBody,
  filledSections,
  groupByDay,
  groupByProject,
  leversOf,
  needsOf,
  snoozeLatest,
  snoozePresets,
  type DeskEntry,
  type Item,
} from "./logic";

function item(kind: string, extra: Partial<Item> = {}): Item {
  return {
    id: 7,
    project_id: "p1",
    kind,
    title: "A title",
    state: "open",
    filed_by: "agent",
    fields: {},
    recommendation: "",
    if_declined: "",
    basis: null,
    actions: ["approve", "deny"],
    deadline: null,
    default_outcome: null,
    outcome: null,
    chairman_note: null,
    waits_on_you: true,
    opened_at: "2031-05-01T10:00:00Z",
    closed_at: null,
    ...extra,
  };
}

describe("needsOf", () => {
  it.each([
    ["proposed scope", "accept", { confirm: false }],
    ["proposed scope", "accept anyway", { note: "optional", confirm: true }],
    ["proposed scope", "decline", { note: "optional", confirm: true }],
    ["proposed commitment", "accept", { date: "optional", confirm: false }],
    ["verdict", "pass", { confirm: false }],
    ["verdict", "reject", { note: "required", confirm: true }],
    ["reserve draw", "deny", { note: "optional", confirm: true }],
    ["approval: capacity", "approve", { amount: "optional", confirm: false }],
    ["approval: spend", "approve", { confirm: false }],
    ["budget checkpoint", "raise the budget", { amount: "required", confirm: false }],
    ["budget checkpoint", "land", { confirm: false }],
    ["question", "answer", { answer: true, confirm: false }],
    ["heads-up", "acknowledge", { confirm: false }],
  ])("%s, %s", (kind, action, needs) => {
    expect(needsOf(kind, action)).toEqual(needs);
  });

  it("opens a form for anything that needs an input or a second thought, and for nothing else", () => {
    expect(asksFirst(needsOf("approval: spend", "approve"))).toBe(false);
    expect(asksFirst(needsOf("approval: spend", "deny"))).toBe(true);
    expect(asksFirst(needsOf("approval: capacity", "approve"))).toBe(true);
    expect(asksFirst(needsOf("question", "answer"))).toBe(true);
  });
});

describe("decideBody", () => {
  it("sends only the action when nothing was filled in", () => {
    expect(decideBody(item("approval: spend"), "approve", {})).toEqual({ project_id: "p1", item_id: 7, action: "approve" });
  });

  it("asks for an amount to raise the budget, and takes whole numbers only", () => {
    const checkpoint = item("budget checkpoint");
    expect(typeof decideBody(checkpoint, "raise the budget", {})).toBe("string");
    expect(typeof decideBody(checkpoint, "raise the budget", { amount: "1.5" })).toBe("string");
    expect(decideBody(checkpoint, "raise the budget", { amount: " 5000 " })).toMatchObject({ amount: 5000 });
  });

  it("leaves an optional amount out when empty, and refuses one that is not a number", () => {
    const capacity = item("approval: capacity");
    expect(decideBody(capacity, "approve", { amount: "" })).not.toHaveProperty("amount");
    expect(decideBody(capacity, "approve", { amount: "3" })).toMatchObject({ amount: 3 });
    expect(typeof decideBody(capacity, "approve", { amount: "many" })).toBe("string");
  });

  it("needs a note to reject a verdict", () => {
    const verdict = item("verdict");
    expect(typeof decideBody(verdict, "reject", { note: "  " })).toBe("string");
    expect(decideBody(verdict, "reject", { note: " Not three steps. " })).toMatchObject({ note: "Not three steps." });
  });

  it("answers a question with an option, a note, or both, and not with neither", () => {
    const question = item("question");
    expect(typeof decideBody(question, "answer", {})).toBe("string");
    expect(decideBody(question, "answer", { option: 2 })).toMatchObject({ option: 2 });
    expect(decideBody(question, "answer", { note: "Ask the venue." })).toMatchObject({ note: "Ask the venue." });
  });

  it("sends a date of the person's own with a commitment, as the end of that day", () => {
    const body = decideBody(item("proposed commitment"), "accept", { date: "2031-05-20" });
    expect(body).toMatchObject({ date: new Date("2031-05-20T23:59:59").toISOString() });
    expect(decideBody(item("proposed commitment"), "accept", {})).not.toHaveProperty("date");
  });
});

describe("snoozePresets", () => {
  const now = new Date(2031, 4, 20, 14, 30);
  const hours = (count: number): string => new Date(now.getTime() + count * 60 * 60 * 1000).toISOString();

  it("offers an hour, tomorrow morning and three days", () => {
    const presets = snoozePresets(now, null);
    expect(presets.map((preset) => preset.id)).toEqual(["hour", "tomorrow", "threeDays"]);
    expect(presets[0]?.until.getTime()).toBe(now.getTime() + 60 * 60 * 1000);
    expect(presets[1]?.until).toEqual(new Date(2031, 4, 21, 9, 0));
    expect(presets[2]?.until.getTime()).toBe(now.getTime() + 3 * 24 * 60 * 60 * 1000);
  });

  it("allows every preset when there is no deadline: all are within a week", () => {
    expect(snoozePresets(now, null).every((preset) => preset.allowed)).toBe(true);
    expect(snoozeLatest(now, null).getTime()).toBe(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  });

  it.each([
    [0.5, [false, false, false]],
    [1, [true, false, false]],
    [24, [true, true, false]],
    [72, [true, true, true]],
  ])("with a deadline %s hours away", (away, allowed) => {
    expect(snoozePresets(now, hours(away)).map((preset) => preset.allowed)).toEqual(allowed);
  });

  it("allows nothing once the deadline has passed", () => {
    expect(snoozePresets(now, hours(-1)).some((preset) => preset.allowed)).toBe(false);
  });
});

describe("deadlineText", () => {
  const when = (iso: string): string => `<${iso}>`;

  it.each([
    ["2031-05-20T10:00:00Z", "The CEO goes ahead.", "Answer by <2031-05-20T10:00:00Z>. If you do nothing: The CEO goes ahead."],
    ["2031-05-20T10:00:00Z", null, "Answer by <2031-05-20T10:00:00Z>."],
    [null, "It stays proposed.", "No deadline. If you do nothing: It stays proposed."],
    ["2031-05-20T10:00:00Z", "decline", "Answer by <2031-05-20T10:00:00Z>. If you do nothing: it is declined."],
    [null, "to a reviewer", "No deadline. If you do nothing: it goes to a reviewer."],
    [null, "  ", "No deadline. This waits until you answer."],
    [null, null, "No deadline. This waits until you answer."],
  ])("deadline %s, default %s", (deadline, outcome, text) => {
    expect(deadlineText(deadline, outcome, when)).toBe(text);
  });
});

describe("groupByDay", () => {
  const at = (day: number, hour: number): string => new Date(2031, 4, day, hour).toISOString();

  it("groups by the viewer's calendar day, earliest first, in time order within a day", () => {
    const groups = groupByDay([
      { at: at(21, 9), what: "c" },
      { at: at(20, 23), what: "b" },
      { at: at(20, 0), what: "a" },
      { at: at(22, 12), what: "d" },
    ]);
    expect(groups.map((group) => [group.day, group.lines.map((line) => line.what)])).toEqual([
      ["2031-05-20", ["a", "b"]],
      ["2031-05-21", ["c"]],
      ["2031-05-22", ["d"]],
    ]);
    expect(groups[0]?.date.getDate()).toBe(20);
  });

  it("returns nothing for no lines", () => {
    expect(groupByDay([])).toEqual([]);
  });
});

describe("groupByProject", () => {
  it("keeps the server's order of projects and of entries", () => {
    const entry = (project: string, title: string): DeskEntry => ({
      project_id: project,
      project_name: `Project ${project}`,
      what: "question",
      title,
      deadline: null,
      item: null,
    });
    const groups = groupByProject([entry("b", "1"), entry("a", "2"), entry("b", "3")]);
    expect(groups.map((group) => [group.name, group.entries.map((each) => each.title)])).toEqual([
      ["Project b", ["1", "3"]],
      ["Project a", ["2"]],
    ]);
  });
});

describe("filledSections", () => {
  it("leaves empty lists out and keeps the given order", () => {
    const sections = { "what happens next": ["A review on Friday."], "what moved": [], "what waits on you": ["A question"] };
    expect(filledSections(sections, AWAY_SECTIONS)).toEqual([
      { name: "what waits on you", lines: ["A question"] },
      { name: "what happens next", lines: ["A review on Friday."] },
    ]);
    expect(filledSections(null, AWAY_SECTIONS)).toEqual([]);
  });
});

describe("item helpers", () => {
  it("offers more time on open approvals and assists only", () => {
    expect(canExtend(item("approval: legal"))).toBe(true);
    expect(canExtend(item("assist", { actions: ["done", "cannot"] }))).toBe(true);
    expect(canExtend(item("question", { actions: ["answer"] }))).toBe(false);
    expect(canExtend(item("approval: legal", { actions: [] }))).toBe(false);
  });

  it("reads the levers of a review and skips anything else", () => {
    const fields = { levers: [{ lever: "cut", reason: "Too much." }, "noise", { lever: "add" }] };
    expect(leversOf(fields, "levers")).toEqual([
      { lever: "cut", reason: "Too much." },
      { lever: "add", reason: "" },
    ]);
    expect(leversOf(fields, "previous_levers")).toEqual([]);
  });
});
