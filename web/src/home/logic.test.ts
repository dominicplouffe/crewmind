/** HUM-10: Home groups what waits by how soon it falls due, and says so in one sentence. */
import { describe, expect, it } from "vitest";
import type { DeskEntry } from "../needs/summary";
import { groupOf, inboxGroups, requirementProgress, summaryLine } from "./logic";

const NOW = Date.parse("2026-11-23T12:00:00Z");
const HOUR = 3600 * 1000;

function entry(id: number, hours: number | null, project = "p1"): DeskEntry {
  return {
    project_id: project,
    project_name: project,
    what: "question",
    title: `Item ${id}`,
    deadline: hours === null ? null : new Date(NOW + hours * HOUR).toISOString(),
    item: null,
  };
}

describe("groupOf", () => {
  it.each([
    [-1, "overdue"],
    [0, "overdue"],
    [1, "today"],
    [24, "today"],
    [25, "week"],
    [7 * 24, "week"],
    [7 * 24 + 1, "later"],
    [null, "later"],
  ] as const)("%s hours from now → %s", (hours, group) => {
    expect(groupOf(entry(1, hours), NOW)).toBe(group);
  });
});

describe("inboxGroups", () => {
  it("orders the groups by urgency, soonest first inside each, and leaves empty ones out", () => {
    const groups = inboxGroups([entry(1, null), entry(2, 30), entry(3, -2), entry(4, 5), entry(5, 2)], NOW);
    expect(groups.map((group) => [group.key, group.entries.map((one) => one.title)])).toEqual([
      ["overdue", ["Item 3"]],
      ["today", ["Item 5", "Item 4"]],
      ["week", ["Item 2"]],
      ["later", ["Item 1"]],
    ]);
  });
});

describe("summaryLine", () => {
  it("answers first: how many, and the soonest", () => {
    expect(summaryLine([entry(1, 5), entry(2, 72), entry(3, null)], 1, NOW)).toBe("3 decisions wait on you, the soonest in 5 hours.");
  });

  it("says when some are overdue, and across how many projects", () => {
    expect(summaryLine([entry(1, -3), entry(2, 5, "p2")], 2, NOW)).toBe("2 decisions wait on you across 2 projects, one is overdue.");
  });

  it("says nothing needs you when nothing does, and leaves out a soonest it does not have", () => {
    expect(summaryLine([], 0, NOW)).toBe("Nothing needs you right now.");
    expect(summaryLine([entry(1, null)], 1, NOW)).toBe("1 decision waits on you.");
  });
});

describe("requirementProgress", () => {
  it("counts accepted scope and what of it is met, and nothing when the plan has not loaded", () => {
    const states = ["met", "met", "in progress", "accepted", "checking", "proposed", "cut", "declined"];
    expect(requirementProgress(states.map((state) => ({ state })))).toEqual({ met: 2, total: 5 });
    expect(requirementProgress(undefined)).toEqual({ met: 0, total: 0 });
  });
});
