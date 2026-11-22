import { describe, expect, it } from "vitest";
import {
  canExtend,
  durationText,
  finishAction,
  groupByStage,
  isSettled,
  readReceipt,
  readScorecard,
  requirementActions,
  timeRows,
  toMoment,
  wholeNumber,
} from "./logic";

describe("groupByStage", () => {
  it("lists stages lowest first and each stage in id order", () => {
    const groups = groupByStage([
      { id: 4, stage: 2 },
      { id: 3, stage: 1 },
      { id: 1, stage: 2 },
      { id: 2, stage: 1 },
      { id: 5, stage: 10 },
    ]);
    expect(groups.map((group) => [group.stage, group.rows.map((row) => row.id)])).toEqual([
      [1, [2, 3]],
      [2, [1, 4]],
      [10, [5]],
    ]);
  });

  it("gives no groups for no requirements", () => {
    expect(groupByStage([])).toEqual([]);
  });
});

describe("requirementActions", () => {
  it.each([
    ["proposed", "command", ["accept", "decline"]],
    ["accepted", "command", ["cut", "estimate"]],
    ["in progress", "observable", ["cut", "estimate"]],
    ["checking", "observable", ["pass", "reject"]],
    ["checking", "command", []],
    ["checking", "metric", []],
    ["met", "command", ["reopen"]],
    ["cut", "observable", ["reopen"]],
    ["declined", "command", []],
    ["a state from a newer server", "command", []],
  ])("a requirement that is %s with a %s test offers %j", (state, test_kind, actions) => {
    expect(requirementActions({ state, test_kind })).toEqual(actions);
  });
});

describe("isSettled", () => {
  it("is true for met, cut and declined only", () => {
    expect(["met", "cut", "declined"].map(isSettled)).toEqual([true, true, true]);
    expect(["proposed", "accepted", "in progress", "checking"].map(isSettled)).toEqual([false, false, false, false]);
  });
});

describe("canExtend", () => {
  it("offers more time only to an expired bet that has not had any", () => {
    expect(canExtend({ state: "expired", extended: false })).toBe(true);
    expect(canExtend({ state: "expired", extended: true })).toBe(false);
    expect(canExtend({ state: "active", extended: false })).toBe(false);
    expect(canExtend({ state: "killed", extended: false })).toBe(false);
  });
});

describe("durationText", () => {
  it.each([
    [0, "0 minutes"],
    [60, "1 minute"],
    [59 * 60, "59 minutes"],
    [3600, "1 hour"],
    [5400, "1.5 hours"],
    [47 * 3600, "47 hours"],
    [48 * 3600, "2 days"],
    [60 * 3600, "2.5 days"],
    [10 * 86400, "10 days"],
    [-5, "0 minutes"],
  ])("words %d seconds as %s", (seconds, text) => {
    expect(durationText(seconds)).toBe(text);
  });
});

describe("timeRows", () => {
  it("keeps the server's order and gives each row its share", () => {
    expect(timeRows({ working: 300, "waiting on the chairman": 100, reviewing: 0 })).toEqual([
      { name: "working", seconds: 300, percent: 75 },
      { name: "waiting on the chairman", seconds: 100, percent: 25 },
      { name: "reviewing", seconds: 0, percent: 0 },
    ]);
  });

  it("gives every row no share when no time was counted, and no rows for nothing", () => {
    expect(timeRows({ working: 0 })).toEqual([{ name: "working", seconds: 0, percent: 0 }]);
    expect(timeRows(null)).toEqual([]);
  });
});

describe("finishAction", () => {
  it.each([
    ["deliver", "ready", "sign_off"],
    ["deliver", "running", null],
    ["deliver", "draft", null],
    ["explore", "running", "end"],
    ["explore", "held", "end"],
    ["explore", "draft", null],
    ["operate", "running", "complete"],
    ["operate", "paused", "complete"],
    ["operate", "stopped", null],
    ["deliver", "completed", "reopen"],
    ["explore", "completed", "reopen"],
    ["operate", "completed", "reopen"],
    ["something else", "running", null],
  ])("a %s project that is %s offers %s", (type, state, action) => {
    expect(finishAction(type, state)).toBe(action);
  });
});

describe("toMoment", () => {
  it("reads a day as the end of that day and a day with a time as that time, in the viewer's time zone", () => {
    expect(toMoment("2026-03-04")).toBe(new Date(2026, 2, 4, 23, 59, 59).toISOString());
    expect(toMoment("2026-03-04T09:30")).toBe(new Date(2026, 2, 4, 9, 30).toISOString());
  });

  it("gives null for an empty or unreadable field", () => {
    expect(toMoment("")).toBeNull();
    expect(toMoment("soon")).toBeNull();
  });
});

describe("wholeNumber", () => {
  it("reads whole numbers at or above the least allowed, and nothing else", () => {
    expect(wholeNumber(" 12 ")).toBe(12);
    expect(wholeNumber("0")).toBeNull();
    expect(wholeNumber("0", 0)).toBe(0);
    expect(wholeNumber("1.5")).toBeNull();
    expect(wholeNumber("-3")).toBeNull();
    expect(wholeNumber("")).toBeNull();
  });
});

describe("readScorecard", () => {
  it("reads the counts and leaves out what it does not know", () => {
    expect(readScorecard({ cycle: 2, recurring_met: 1, recurring_total: 3, work_runs: 7, tokens: 9000, requirements: [] })).toEqual({
      recurringMet: 1,
      recurringTotal: 3,
      workRuns: 7,
      tokens: 9000,
    });
  });

  it("gives null when there is no scorecard or it has another shape", () => {
    expect(readScorecard(null)).toBeNull();
    expect(readScorecard({ recurring_met: "one" })).toBeNull();
    expect(readScorecard([1, 2])).toBeNull();
  });
});

describe("readReceipt", () => {
  it("reads a Deliver receipt", () => {
    const receipt = readReceipt({
      requirements: [{ id: 1, text: "A page", state: "met", estimate_runs: 3, actual_runs: 4, actual_tokens: 1200 }],
      tokens: { input: 1000, output: 200, cache_write: 0, cache_read: 50, counted: 1200 },
      reserve_drawn: 0,
      wall_clock_seconds: 7200,
      time: { to_first_task_seconds: 60, to_first_deliverable_seconds: null, to_done_seconds: 7200, where: { working: 7200 } },
      commitment: { kept: true, date: "2026-03-04T00:00:00Z", resets: 1, state: "met" },
    });
    expect(receipt?.requirements).toEqual([
      { id: 1, text: "A page", state: "met", estimateRuns: 3, actualRuns: 4, actualTokens: 1200 },
    ]);
    expect(receipt?.tokens[0]).toEqual(["input", 1000]);
    expect(receipt?.tokens).toHaveLength(5);
    expect(receipt?.wallClockSeconds).toBe(7200);
    expect(receipt?.time).toEqual({
      toFirstTask: 60,
      toFirstDeliverable: null,
      toDone: 7200,
      where: [{ name: "working", seconds: 7200, percent: 100 }],
    });
    expect(receipt?.commitment).toEqual({ kept: true, date: "2026-03-04T00:00:00Z", resets: 1, state: "met" });
    expect(receipt?.bets).toEqual([]);
    expect(receipt?.cycles).toEqual([]);
  });

  it("reads the Explore and Operate parts, and a receipt with no commitment", () => {
    const receipt = readReceipt({
      commitment: null,
      bets: [{ id: 2, statement: "People want it", state: "confirmed", finding: "finding-2.md" }],
      findings_report: "findings-report.md",
      cycles: [{ number: 1, state: "completed" }],
      final_scorecard: { recurring_met: 2, recurring_total: 2, work_runs: 5, tokens: 10 },
    });
    expect(receipt?.commitment).toBeNull();
    expect(receipt?.bets).toEqual([{ id: 2, statement: "People want it", state: "confirmed", finding: "finding-2.md" }]);
    expect(receipt?.findingsReport).toBe("findings-report.md");
    expect(receipt?.cycles).toEqual([{ number: 1, state: "completed" }]);
    expect(receipt?.finalScorecard?.recurringMet).toBe(2);
  });

  it("gives null when there is no receipt", () => {
    expect(readReceipt(null)).toBeNull();
    expect(readReceipt("receipt")).toBeNull();
  });
});
