/**
 * The arithmetic behind the burn-up chart (GOV-1, PLN-5): cumulative tokens over time from runs,
 * and a straight projection at the measured pace. Display only: the pace and the wall come from
 * the server; nothing here decides anything.
 */
import type { Schemas } from "../api/client";

type Run = Schemas["RunItem"];

export interface BurnPoint {
  at: number;
  total: number;
}

const HOUR = 3_600_000;
const MINUTE = 60_000;
/** A wall this many times above everything drawn is noted in words instead of squashing the line. */
const WALL_FAR = 4;

/** Cumulative tokens counted, one step per run, ending at `now` with the budget's own total. */
export function burnSeries(runs: readonly Run[], spent: number, now: number): BurnPoint[] {
  const counted = runs
    .filter((run) => run.tokens_counted > 0)
    .map((run) => ({ at: Date.parse(run.ended_at ?? run.started_at ?? run.queued_at), tokens: run.tokens_counted }))
    .filter((run) => !Number.isNaN(run.at))
    .sort((a, b) => a.at - b.at);
  const starts = runs.map((run) => Date.parse(run.started_at ?? run.queued_at)).filter((at) => !Number.isNaN(at));
  const first = counted[0];
  if (!first) return spent > 0 ? [{ at: now - HOUR, total: 0 }, { at: now, total: spent }] : [];
  const points: BurnPoint[] = [{ at: Math.min(first.at, ...starts), total: 0 }];
  let total = 0;
  for (const run of counted) {
    total += run.tokens;
    points.push({ at: run.at, total });
  }
  // Spend the runs list does not explain (or a run still going) shows as the step to now.
  const end = Math.max(now, counted[counted.length - 1]?.at ?? now);
  points.push({ at: end, total: Math.max(total, spent) });
  return points;
}

export interface BurnPlan {
  points: BurnPoint[];
  current: BurnPoint;
  projection: { to: BurnPoint; hitsWall: boolean } | null;
  xMin: number;
  xMax: number;
  yMax: number;
  /** False when the wall is far above everything drawn; the chart then says so in words. */
  wallVisible: boolean;
}

export interface BurnInput {
  points: BurnPoint[];
  wall: number;
  burnRate: number | null;
  projectedAt: string | null;
}

export function burnPlan({ points, wall, burnRate, projectedAt }: BurnInput): BurnPlan | null {
  const current = points[points.length - 1];
  const start = points[0];
  if (!current || !start) return null;
  const xMin = start.at;
  const elapsed = Math.max(current.at - xMin, 10 * MINUTE);
  let projection: BurnPlan["projection"] = null;
  let xMax = current.at + elapsed * 0.04;

  if (burnRate && burnRate > 0) {
    const finish = projectedAt ? Date.parse(projectedAt) : NaN;
    const wallAt = wall > current.total ? current.at + ((wall - current.total) / burnRate) * HOUR : current.at;
    // Draw to the projected finish, or else towards the wall, within a window the eye can compare.
    let end = Number.isNaN(finish) || finish <= current.at ? wallAt : finish;
    end = Math.min(Math.max(end, current.at + elapsed * 0.25), current.at + elapsed * 3);
    const hitsWall = wallAt <= end;
    if (hitsWall) end = wallAt;
    const total = hitsWall ? wall : current.total + (burnRate * (end - current.at)) / HOUR;
    projection = { to: { at: end, total }, hitsWall };
    xMax = end;
  }

  const need = Math.max(current.total, projection?.to.total ?? 0, 1);
  const wallVisible = wall > 0 && wall <= need * WALL_FAR;
  const yMax = wallVisible ? wall * 1.06 : niceCeil(need * 1.15);
  return { points, current, projection, xMin, xMax, yMax, wallVisible };
}

/** The smallest 1, 2, 2.5 or 5 times a power of ten at or above `value`. */
export function niceStep(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const factor of [1, 2, 2.5, 5, 10]) if (factor * power >= value) return factor * power;
  return 10 * power;
}

export function niceCeil(value: number): number {
  const step = niceStep(value / 5);
  return Math.max(step, Math.ceil(value / step) * step);
}

/** Evenly spaced round values from 0 up to `max`. */
export function niceTicks(max: number, count = 4): number[] {
  const step = niceStep(max / count);
  const ticks: number[] = [];
  for (let value = 0; value <= max + step * 1e-9; value += step) ticks.push(value);
  return ticks;
}

/** Hours of active work the remaining budget covers at the measured pace, or null when unmeasured. */
export function hoursLeft(remaining: number, burnRate: number | null): number | null {
  if (!burnRate || burnRate <= 0) return null;
  return Math.max(0, remaining) / burnRate;
}

/** The point at or just before `at` (the line is a step: totals change when a run ends). */
export function pointAt(points: readonly BurnPoint[], at: number): BurnPoint | null {
  let found: BurnPoint | null = null;
  for (const point of points) {
    if (point.at <= at) found = point;
    else break;
  }
  return found ?? points[0] ?? null;
}
