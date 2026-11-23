/** PLN-5, GOV-1, CHAT-18, EXE-4: the headline, progress, projection, budget pace and burn-up arithmetic, in words. */
import { describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { burnPlan, burnSeries, hoursLeft, niceCeil, niceStep, niceTicks, pointAt, tickUnit, timeTicks } from "./burn";
import { budgetWords, headlineOf, progressOf, projectionSentence, requirementRows, taskCount, type HeadlineInput } from "./logic";

const NOW = Date.parse("2026-11-22T12:00:00Z");
const at = (minutes: number): string => new Date(NOW + minutes * 60_000).toISOString();

function pace(extra: Partial<Schemas["PaceView"]>): Schemas["PaceView"] {
  return { burn_rate: null, projected_at: null, projected_spend: null, projection: "", projection_kind: "unknown", throughput: null, ...extra };
}

function run(minutes: number, tokens: number): Schemas["RunItem"] {
  return {
    run_id: String(minutes),
    seat: "CEO",
    kind: "work",
    state: "finished",
    attempt: 1,
    reasons: [],
    model: null,
    provider: null,
    queued_at: at(minutes - 1),
    leased_at: null,
    started_at: at(minutes - 1),
    ended_at: at(minutes),
    end_detail: null,
    tokens_counted: tokens,
  };
}

describe("progressOf", () => {
  it("groups states into four stages and leaves cut and declined out", () => {
    const states = ["proposed", "accepted", "in progress", "checking", "met", "met", "cut", "declined"];
    const progress = progressOf(states.map((state) => ({ state })));
    expect(Object.fromEntries(progress.segments.map((segment) => [segment.key, segment.value]))).toEqual({
      done: 2,
      active: 2,
      todo: 1,
      proposed: 1,
    });
    expect(progress.counted).toBe(6);
    expect(progress.excluded).toBe(2);
  });
});

describe("projectionSentence", () => {
  it.each([
    [pace({ projection_kind: "nothing left", projected_at: at(0) }), 0, "Nothing accepted is left to do."],
    [pace({ projection_kind: "nothing left" }), 2, "Nothing accepted is left to do. 2 proposed requirements wait for a decision."],
    [pace({ projection_kind: "unknown" }), 0, "Not enough finished work yet to project a finish."],
    [pace({ projection_kind: "best case", projected_at: at(360) }), 0, "At best the open work takes about 6 h of active work."],
  ])("%#", (value, proposed, text) => {
    expect(projectionSentence(value, proposed, NOW)).toBe(text);
  });
  it("names the date for a measured projection", () => {
    expect(projectionSentence(pace({ projection_kind: "measured", projected_at: at(90) }), 0, NOW)).toMatch(
      /^At the measured pace the open work takes about 1 h 30 min of active work, finishing around .+\.$/,
    );
  });
  it("never says a finish seconds away; a projection minutes away is said as minutes", () => {
    const text = projectionSentence(pace({ projection_kind: "measured", projected_at: new Date(NOW + 1000).toISOString() }), 1, NOW);
    expect(text).not.toMatch(/\d+ s\b/);
    expect(text).toMatch(/^At the measured pace the open work needs only minutes of running time/);
    expect(text).toMatch(/1 proposed requirement waits for a decision\.$/);
  });
});

describe("burnSeries", () => {
  it("adds up tokens in run order and ends at now with the budget total", () => {
    const points = burnSeries([run(-10, 200), run(-30, 100)], 400, NOW);
    expect(points.map((point) => point.total)).toEqual([0, 100, 300, 400]);
    expect(points[points.length - 1]?.at).toBe(NOW);
  });
  it("is empty with nothing spent", () => {
    expect(burnSeries([], 0, NOW)).toEqual([]);
  });
});

describe("burnPlan", () => {
  const points = burnSeries([run(-60, 1000)], 1000, NOW);

  it("projects at the pace until it meets the wall", () => {
    const plan = burnPlan({ points, wall: 3000, burnRate: 1000, projectedAt: null });
    expect(plan?.projection?.hitsWall).toBe(true);
    expect(plan?.projection?.to.total).toBe(3000);
    expect(plan?.projection?.to.at).toBe(NOW + 2 * 3_600_000);
    expect(plan?.wallVisible).toBe(true);
  });

  it("notes a far wall in words instead of squashing the line", () => {
    const plan = burnPlan({ points, wall: 20_000_000, burnRate: 1000, projectedAt: null });
    expect(plan?.wallVisible).toBe(false);
    expect(plan?.projection?.hitsWall).toBe(false);
    expect(plan?.yMax).toBeGreaterThan(plan?.projection?.to.total ?? 0);
  });

  it("draws no projection without a measured pace", () => {
    expect(burnPlan({ points, wall: 3000, burnRate: null, projectedAt: null })?.projection).toBeNull();
    expect(burnPlan({ points: [], wall: 3000, burnRate: 10, projectedAt: null })).toBeNull();
  });
});

describe("scales", () => {
  it.each([
    [0.7, 1],
    [3, 5],
    [2.2, 2.5],
    [1400, 2000],
  ])("niceStep(%s) = %s", (value, step) => {
    expect(niceStep(value)).toBe(step);
  });
  it("makes round ticks", () => {
    expect(niceTicks(1000)).toEqual([0, 250, 500, 750, 1000]);
    expect(niceCeil(1150)).toBe(1250);
  });
  it("finds the step at a time and the hours left", () => {
    const points = [
      { at: 0, total: 0 },
      { at: 10, total: 5 },
      { at: 20, total: 9 },
    ];
    expect(pointAt(points, 15)?.total).toBe(5);
    expect(hoursLeft(1000, 100)).toBe(10);
    expect(hoursLeft(1000, null)).toBeNull();
  });
});

describe("headlineOf", () => {
  const base: HeadlineInput = {
    state: "running",
    holds: [],
    atWall: false,
    requirements: [{ state: "in progress" }, { state: "in progress" }, { state: "in progress" }, { state: "proposed" }],
    tasks: [
      { state: "done", requirement_id: 1, title: "Copy", reason: null },
      { state: "done", requirement_id: 3, title: "Providers", reason: null },
      { state: "claimed", requirement_id: 1, title: "FAQ", reason: null },
      { state: "review", requirement_id: 2, title: "Pricing", reason: null },
      { state: "killed", requirement_id: 2, title: "Old", reason: null },
    ],
    spent: 1_100_000,
    wall: 2_000_000,
  };

  it.each<[string, Partial<HeadlineInput>, string, string]>([
    ["under way", {}, "Under way", "3 of 4 requirements under way, 2 of 4 tasks done, 55% of the budget used."],
    ["draft", { state: "draft" }, "Not started", "The project is still a draft."],
    ["no requirements", { requirements: [], tasks: [] }, "Getting started", "The CEO has not proposed requirements yet."],
    [
      "held",
      { state: "held", holds: [{ reason: "chairman", lifts: "/resume" }] },
      "On hold",
      "Because you put it on hold. It lifts by /resume. 3 of 4 requirements under way, 2 of 4 tasks done, 55% of the budget used.",
    ],
    [
      "all met",
      { requirements: [{ state: "met" }, { state: "met" }], tasks: [{ state: "done", requirement_id: 1, title: "A", reason: null }] },
      "Every requirement met",
      "All 2 requirements met, 1 of 1 task done, 55% of the budget used.",
    ],
    ["stopped", { state: "stopped" }, "Stopped", "3 of 4 requirements under way, 2 of 4 tasks done, 55% of the budget used."],
  ])("CHAT-18 %s", (_name, extra, lead, facts) => {
    const headline = headlineOf({ ...base, ...extra });
    expect(headline.lead).toBe(lead);
    expect(headline.facts).toBe(facts);
  });

  it("names the first blocked task with its reason, and says Blocked when nothing else is open", () => {
    const blocked = { state: "blocked", requirement_id: 3, title: "Wire the sign-up form", reason: "Waiting for approval." };
    const some = headlineOf({ ...base, tasks: [...base.tasks, blocked] });
    expect(some.lead).toBe("Under way");
    expect(some.tone).toBe("attention");
    expect(some.blocked).toEqual({ title: "Wire the sign-up form", reason: "Waiting for approval.", others: 0 });
    const only = headlineOf({ ...base, tasks: [base.tasks[0]!, blocked] });
    expect(only.lead).toBe("Blocked");
  });

  it("counts met and under way requirements together", () => {
    const headline = headlineOf({ ...base, requirements: [{ state: "met" }, { state: "checking" }, { state: "accepted" }] });
    expect(headline.facts).toMatch(/^1 of 3 requirements met, 1 under way, /);
  });
});

describe("requirementRows and taskCount", () => {
  it("PLN-5 gives each counted requirement its tasks done out of all, killed left out", () => {
    const rows = requirementRows(
      [
        { id: 1, text: "Landing page", state: "in progress" },
        { id: 2, text: "Pricing", state: "accepted" },
        { id: 3, text: "Old idea", state: "cut" },
      ],
      [
        { state: "done", requirement_id: 1, title: "a", reason: null },
        { state: "claimed", requirement_id: 1, title: "b", reason: null },
        { state: "killed", requirement_id: 1, title: "c", reason: null },
      ],
    );
    expect(rows.map((row) => [row.id, row.stateWord, row.done, row.total])).toEqual([
      [1, "In progress", 1, 2],
      [2, "Not started", 0, 0],
    ]);
  });
  it("does not count a task closed unread as done (P5)", () => {
    expect(taskCount([{ state: "closed unread" }, { state: "done" }])).toEqual({ done: 1, total: 2 });
  });
});

describe("budgetWords", () => {
  it("GOV-1 states the pace and what the rest covers, or what is known without a pace", () => {
    const words = budgetWords({ spent: 1_094_100, wall: 2_000_000, remaining: 905_900 }, 950_050);
    expect(words.used).toBe("1.1M of 2M tokens");
    expect(words.share).toBe("55%");
    expect(words.pace).toBe("About 950K tokens per active hour. The 905.9K left covers about 57 min of active work at that pace.");
    const none = budgetWords({ spent: 10, wall: 100, remaining: 90 }, null);
    expect(none.pace).toBe("The pace is measured once a few work runs finish.");
    expect(none.paceShort).toBeNull();
  });
});

describe("timeTicks", () => {
  const start = Date.parse("2026-11-22T12:00:07Z");
  it.each([
    ["15 seconds", 15_000, "second"],
    ["4 minutes", 4 * 60_000, "minute"],
    ["5 hours", 5 * 3_600_000, "minute"],
    ["9 days", 9 * 86_400_000, "day"],
  ])("labels a span of %s without repeats, in at most five ticks", (_name, span, unit) => {
    const ticks = timeTicks(start, start + span, 5);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    expect(ticks.length).toBeLessThanOrEqual(5);
    expect(new Set(ticks.map((tick) => tick.label)).size).toBe(ticks.length);
    expect(ticks.every((tick) => tick.at >= start && tick.at <= start + span + 1)).toBe(true);
    const step = (ticks[1]?.at ?? 0) - (ticks[0]?.at ?? 0);
    expect(tickUnit(step)).toBe(unit);
  });
  it("puts ticks on round times", () => {
    const ticks = timeTicks(start, start + 20 * 60_000, 5);
    expect(ticks.every((tick) => tick.at % (5 * 60_000) === 0)).toBe(true);
  });
});
