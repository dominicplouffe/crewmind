/** PLN-5, GOV-1, CHAT-19: progress, projection, burn-up arithmetic and the timeline, in words. */
import { describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { burnPlan, burnSeries, hoursLeft, niceCeil, niceStep, niceTicks, pointAt } from "./burn";
import { progressOf, projectionSentence, tidy, timelineOf } from "./logic";

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
    [pace({ projection_kind: "nothing left" }), 2, "Nothing accepted is left to do. 2 proposed requirements wait for your decision."],
    [pace({ projection_kind: "unknown" }), 0, "Not enough finished work yet to project a finish."],
    [pace({ projection_kind: "best case", projected_at: at(360) }), 0, "Projected to finish in about 6 h (best case)."],
  ])("%#", (value, proposed, text) => {
    expect(projectionSentence(value, proposed, NOW)).toBe(text);
  });
  it("names the date for a measured projection", () => {
    expect(projectionSentence(pace({ projection_kind: "measured", projected_at: at(90) }), 0, NOW)).toMatch(
      /^Projected to finish in about 1 h 30 min, around .+\.$/,
    );
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

describe("timelineOf", () => {
  it("keeps readable lines, newest first, without raw ids", () => {
    const items = [
      { id: 1, at: at(-10), text: "project: created (project 375c7641953f43f39175dbfc44af9b65).", actor: "x", type: "project.created" },
      { id: 2, at: at(-5), text: "A work run is now queued.", actor: "x", type: "run.state_changed" },
      { id: 3, at: at(-1), text: "Directive 1 is now issued.", actor: "x", type: "directive.state_changed" },
    ];
    const lines = timelineOf(items, 12, NOW);
    expect(lines.map((line) => line.text)).toEqual(["Directive 1 is now issued.", "Project: created."]);
    expect(lines[0]?.when).toBe("1 minute ago");
  });
  it("tidies text", () => {
    expect(tidy("member: added (person 6e77205f41954f7c97de581fb3dfc9c6).")).toBe("Member: added.");
  });
});
