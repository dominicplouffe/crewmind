/** CHAT-18, EXE-4, WRK-4: who is doing what, in sentences, from the header and the tasks. */
import { describe, expect, it } from "vitest";
import { nowEntries, plainText } from "./now";

type TaskInput = Parameters<typeof nowEntries>[1][number];

function task(id: number, state: string, title: string, claimant: string | null, reason: string | null = null): TaskInput {
  return { id, state, title, claimant, reason, team: "words" };
}

const TASKS = [
  task(1, "done", "Write the landing-page copy", "Maya"),
  task(2, "claimed", "Write the FAQ", "Maya"),
  task(3, "review", "Build the pricing table", "Theo"),
  task(5, "blocked", "Wire the sign-up form", null, "Waiting for the chairman to approve the email plan."),
  task(6, "ready", "Draft the checklist", null),
  task(7, "checking", "Run the link check", "Priya"),
];

describe("nowEntries", () => {
  it("CHAT-18 tells claimed, blocked and review tasks as sentences, blocked first", () => {
    const entries = nowEntries([], TASKS);
    expect(entries.map((entry) => [entry.status, plainText(entry.parts), entry.note])).toEqual([
      ["blocked", "Wire the sign-up form is blocked", "Waiting for the chairman to approve the email plan."],
      ["review", "Build the pricing table waits for review", "From Theo"],
      ["checking", "Run the link check is being checked", "From Priya"],
      ["claimed", "Maya has Write the FAQ in hand", "Claimed, not running at the moment"],
    ]);
    expect(entries[0]?.noteIsAgentText).toBe(true);
    expect(entries[0]?.seat).toBeNull();
  });

  it("EXE-18 names agents by the name they go by, keeping the seat for the avatar", () => {
    const entries = nowEntries([{ seat: "CEO", run_kind: "chat", doing: "thinking" }], TASKS, (seat) => (seat === "CEO" ? "Lena" : seat));
    expect(plainText(entries[0]?.parts ?? [])).toContain("Lena");
    expect(entries[0]?.seat).toBe("CEO");
  });

  it("EXE-4 puts agents at work first, naming the task a work run is on", () => {
    const entries = nowEntries(
      [
        { seat: "Maya", run_kind: "work", doing: "using web_search" },
        { seat: "CEO", run_kind: "chat", doing: "thinking" },
      ],
      TASKS,
    );
    expect(entries.slice(0, 2).map((entry) => [plainText(entry.parts), entry.note])).toEqual([
      ["Maya is working on Write the FAQ", "Using web search"],
      ["CEO is at work", "Writing a reply in chat"],
    ]);
    // Maya's claimed task is not repeated as "in hand" while she runs.
    expect(entries.filter((entry) => entry.seat === "Maya")).toHaveLength(1);
  });

  it("says nothing when nothing is under way, and gives a blocked task without a reason a plain note", () => {
    expect(nowEntries([], [task(1, "done", "A", "Maya")])).toEqual([]);
    const [entry] = nowEntries([], [task(2, "blocked", "B", "Theo", "  ")]);
    expect(entry?.note).toBe("No reason given.");
    expect(entry?.noteIsAgentText).toBe(false);
  });
});
