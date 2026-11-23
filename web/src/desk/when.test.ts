import { describe, expect, it } from "vitest";
import { namesOf } from "../crew/names";
import { askerOf, deadlineWords, kindLabel } from "./when";

const NOW = Date.parse("2026-11-22T12:00:00Z");
const HOUR = 3600 * 1000;

describe("a decision card's deadline in words (HUM-2)", () => {
  it("says by when, how far off, and what happens if nobody answers", () => {
    const words = deadlineWords(new Date(NOW + 50 * HOUR).toISOString(), "decline", NOW);
    expect(words.line).toMatch(/^Decide by .+ · in 2 days$/);
    expect(words.urgency).toBe("soon");
    expect(words.ifNothing).toBe("If you do nothing: it is declined.");
  });

  it("names urgency in words, not colour alone", () => {
    expect(deadlineWords(new Date(NOW + 2 * HOUR).toISOString(), null, NOW).badge).toBe("Due today");
    const late = deadlineWords(new Date(NOW - 3 * HOUR).toISOString(), "deny", NOW);
    expect(late.badge).toBe("Overdue");
    expect(late.line).toMatch(/^Overdue · was due .+, 3 hours ago$/);
  });

  it("says when there is no deadline, and shows an unknown default as given", () => {
    const words = deadlineWords(null, "something else", NOW);
    expect(words.line).toBe("No deadline · this waits for you");
    expect(words.ifNothing).toBe("If you do nothing: something else");
  });
});

describe("who asks, and what kind of decision it is", () => {
  it("names the CEO for kinds it files, and crewmind for its own", () => {
    expect(askerOf("agent", "proposed scope")).toEqual({ name: "CEO", seat: "CEO", line: "The CEO asks", who: "CEO" });
    expect(askerOf("agent", "assist")).toEqual({ name: "Agent", line: "An agent asks", who: "An agent" });
    expect(askerOf("platform", "verdict")).toEqual({ name: null, line: "crewmind asks", who: "crewmind" });
    expect(askerOf("researcher", "approval: tool permission").line).toBe("researcher asks");
  });

  it("names an agent by the name it goes by, its role second (EXE-18)", () => {
    const nameOf = namesOf([
      { name: "CEO", display_name: "Maya", kind: "ceo", role: "CEO / Project Manager", team: null, lead: false, state: "active", pause_reason: null },
      { name: "research-1", display_name: "Lena", kind: "worker", role: "Researcher", team: "research", lead: true, state: "active", pause_reason: null },
    ]);
    expect(askerOf("agent", "proposed scope", nameOf)).toEqual({ name: "Maya", seat: "CEO", line: "Maya, the CEO, asks", who: "Maya · CEO" });
    expect(askerOf("research-1", "approval: tool permission", nameOf).line).toBe("Lena, the Researcher, asks");
    expect(askerOf("ghost", "question", nameOf).who).toBe("ghost");
  });

  it("uses plain labels for kinds", () => {
    expect(kindLabel("proposed scope")).toBe("Scope proposal");
    expect(kindLabel("approval: spend")).toBe("Spending approval");
    expect(kindLabel("verdict")).toBe("Verdict needed");
    expect(kindLabel("something new")).toBe("Something new");
  });
});
