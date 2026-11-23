/** HUM-10, CHAT-18: one selector over the desk; every count is derived from it. */
import { describe, expect, it } from "vitest";
import { countFor, summarize, titled, urgencyOf, type DeskEntry } from "./summary";

const NOW = Date.parse("2026-11-22T12:00:00Z");

function entry(project: string, id: number, deadline: string | null): DeskEntry {
  return {
    project_id: project,
    project_name: project.toUpperCase(),
    what: "proposed scope",
    title: `Item ${id}`,
    deadline,
    item: null,
  };
}

describe("summarize (HUM-10)", () => {
  const entries = [
    entry("b", 3, null),
    entry("a", 1, "2026-11-25T12:00:00Z"),
    entry("a", 2, "2026-11-22T18:00:00Z"),
  ];

  it("counts every entry once and per project, and the parts add up to the whole", () => {
    const summary = summarize(entries);
    expect(summary.count).toBe(3);
    expect(countFor(summary, "a")).toBe(2);
    expect(countFor(summary, "b")).toBe(1);
    expect(countFor(summary, "missing")).toBe(0);
    const parts = [...summary.byProject.values()].reduce((sum, list) => sum + list.length, 0);
    expect(parts).toBe(summary.count);
  });

  it("puts the soonest deadline first and undated items last", () => {
    expect(summarize(entries).entries.map((item) => item.title)).toEqual(["Item 2", "Item 1", "Item 3"]);
  });

  it("an empty desk is zero everywhere", () => {
    const summary = summarize([]);
    expect(summary.count).toBe(0);
    expect(countFor(summary, "a")).toBe(0);
    expect(titled("Home", summary.count)).toBe("Home");
  });
});

describe("urgencyOf", () => {
  it.each([
    ["2026-11-22T11:00:00Z", "overdue"],
    ["2026-11-22T20:00:00Z", "today"],
    ["2026-11-24T12:00:00Z", "soon"],
    ["2026-12-10T12:00:00Z", "later"],
    [null, "none"],
  ] as const)("%s is %s", (deadline, expected) => {
    expect(urgencyOf({ deadline }, NOW)).toBe(expected);
  });
});

describe("titled", () => {
  it("puts the count in front of the title", () => {
    expect(titled("Home · crewmind", 2)).toBe("(2) Home · crewmind");
  });
});
