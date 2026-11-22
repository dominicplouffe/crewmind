/**
 * Display logic for the Plan panel: requirements grouped by stage, which actions each state offers,
 * how a duration is worded, and how the untyped parts of the server's answer (a scorecard, a receipt)
 * are read. Nothing here decides anything: states come from the server and are only arranged.
 */
import { t } from "../../strings";

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
/** Durations are worded in hours below two days and in days from there. */
const DAYS_FROM = 2 * DAY;

export interface Staged {
  id: number;
  stage: number;
}

export interface StageGroup<T> {
  stage: number;
  rows: T[];
}

/** Groups requirements by stage, lowest stage first, each stage in id order. */
export function groupByStage<T extends Staged>(requirements: readonly T[]): StageGroup<T>[] {
  const groups = new Map<number, T[]>();
  for (const requirement of requirements) {
    groups.set(requirement.stage, [...(groups.get(requirement.stage) ?? []), requirement]);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => left - right)
    .map(([stage, rows]) => ({ stage, rows: [...rows].sort((left, right) => left.id - right.id) }));
}

export type RequirementAction = "accept" | "decline" | "cut" | "estimate" | "pass" | "reject" | "reopen";

/** What the chairman can do to a requirement in this state. A state this page does not know offers nothing. */
export function requirementActions(requirement: { state: string; test_kind: string }): RequirementAction[] {
  switch (requirement.state) {
    case "proposed":
      return ["accept", "decline"];
    case "accepted":
    case "in progress":
      return ["cut", "estimate"];
    case "checking":
      return requirement.test_kind === "observable" ? ["pass", "reject"] : [];
    case "met":
    case "cut":
      return ["reopen"];
    default:
      return [];
  }
}

/** A requirement that is no longer open work: listed more quietly. */
export function isSettled(state: string): boolean {
  return state === "met" || state === "cut" || state === "declined";
}

/** An expired bet can be given more time once. */
export function canExtend(bet: { state: string; extended: boolean }): boolean {
  return bet.state === "expired" && !bet.extended;
}

/** A length of time in words: minutes under an hour, hours under two days, days from there. */
export function durationText(seconds: number): string {
  const length = Math.max(0, seconds);
  if (length < HOUR) return t.plan.duration.minutes(Math.round(length / MINUTE));
  if (length < DAYS_FROM) return t.plan.duration.hours(oneDecimal(length / HOUR));
  return t.plan.duration.days(oneDecimal(length / DAY));
}

function oneDecimal(value: number): number {
  return Math.round(value * 10) / 10;
}

export interface TimeRow {
  /** The server's name for where the time went, shown as given. */
  name: string;
  seconds: number;
  /** 0 to 100: this row's share of all the time, for a bar. */
  percent: number;
}

/** Where the time went, in the server's order, each with its share of the total. */
export function timeRows(where: Record<string, number> | null | undefined): TimeRow[] {
  const entries = Object.entries(where ?? {}).filter(([, seconds]) => typeof seconds === "number");
  const total = entries.reduce((sum, [, seconds]) => sum + Math.max(0, seconds), 0);
  return entries.map(([name, seconds]) => ({
    name,
    seconds,
    percent: total <= 0 ? 0 : Math.round((Math.max(0, seconds) / total) * 100),
  }));
}

export type FinishAction = "sign_off" | "end" | "complete" | "reopen";

const NOT_UNDER_WAY = ["completed", "stopped", "deleting", "deleted", "draft"];

/**
 * The finish action this project offers now, or null. A Deliver project is signed off once it is
 * ready; an Explore project is ended and an Operate project completed while it is under way; a
 * completed project can be reopened.
 */
export function finishAction(type: string, state: string): FinishAction | null {
  if (state === "completed") return "reopen";
  if (type === "deliver") return state === "ready" ? "sign_off" : null;
  if (NOT_UNDER_WAY.includes(state)) return null;
  if (type === "explore") return "end";
  if (type === "operate") return "complete";
  return null;
}

/** The moment a date field names, as the server wants it. A day with no time means the end of that day. */
export function toMoment(value: string): string | null {
  if (!value) return null;
  const date = new Date(value.includes("T") ? value : `${value}T23:59:59`);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** A whole number at or above `least` from a form field, or null when the field does not hold one. */
export function wholeNumber(value: string, least = 1): number | null {
  const text = value.trim();
  if (!/^\d+$/.test(text)) return null;
  const number = Number(text);
  return Number.isSafeInteger(number) && number >= least ? number : null;
}

type Fields = Record<string, unknown>;

function fields(value: unknown): Fields | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}
const numberOf = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const textOf = (value: unknown): string | null => (typeof value === "string" ? value : null);
const listOf = (value: unknown): Fields[] =>
  Array.isArray(value) ? (value as unknown[]).map(fields).filter((row): row is Fields => row !== null) : [];

export interface Scorecard {
  recurringMet: number;
  recurringTotal: number;
  workRuns: number;
  tokens: number;
}

/** A cycle's scorecard, or null when the cycle has none yet or it is not in the shape this page knows. */
export function readScorecard(value: unknown): Scorecard | null {
  const card = fields(value);
  const recurringMet = numberOf(card?.recurring_met);
  const recurringTotal = numberOf(card?.recurring_total);
  if (!card || recurringMet === null || recurringTotal === null) return null;
  return { recurringMet, recurringTotal, workRuns: numberOf(card.work_runs) ?? 0, tokens: numberOf(card.tokens) ?? 0 };
}

export interface ReceiptRequirement {
  id: number;
  text: string;
  state: string;
  estimateRuns: number | null;
  actualRuns: number | null;
  actualTokens: number | null;
}

export interface ReceiptView {
  requirements: ReceiptRequirement[];
  /** Tokens by kind, in the server's order. */
  tokens: [kind: string, count: number][];
  reserveDrawn: number | null;
  wallClockSeconds: number | null;
  time: {
    toFirstTask: number | null;
    toFirstDeliverable: number | null;
    toDone: number | null;
    where: TimeRow[];
  } | null;
  commitment: { kept: boolean; date: string | null; resets: number; state: string } | null;
  bets: { id: number; statement: string; state: string; finding: string | null }[];
  findingsReport: string | null;
  cycles: { number: number; state: string }[];
  finalScorecard: Scorecard | null;
}

/** Reads a receipt the server sends as free-form data. Parts it does not carry are left empty. */
export function readReceipt(value: unknown): ReceiptView | null {
  const receipt = fields(value);
  if (!receipt) return null;
  const time = fields(receipt.time);
  const commitment = fields(receipt.commitment);
  return {
    requirements: listOf(receipt.requirements).map((row) => ({
      id: numberOf(row.id) ?? 0,
      text: textOf(row.text) ?? "",
      state: textOf(row.state) ?? "",
      estimateRuns: numberOf(row.estimate_runs),
      actualRuns: numberOf(row.actual_runs),
      actualTokens: numberOf(row.actual_tokens),
    })),
    tokens: Object.entries(fields(receipt.tokens) ?? {}).flatMap(([kind, count]): [string, number][] => {
      const number = numberOf(count);
      return number === null ? [] : [[kind, number]];
    }),
    reserveDrawn: numberOf(receipt.reserve_drawn),
    wallClockSeconds: numberOf(receipt.wall_clock_seconds),
    time: time
      ? {
          toFirstTask: numberOf(time.to_first_task_seconds),
          toFirstDeliverable: numberOf(time.to_first_deliverable_seconds),
          toDone: numberOf(time.to_done_seconds),
          where: timeRows(fields(time.where) as Record<string, number> | null),
        }
      : null,
    commitment: commitment
      ? {
          kept: commitment.kept === true,
          date: textOf(commitment.date),
          resets: numberOf(commitment.resets) ?? 0,
          state: textOf(commitment.state) ?? "",
        }
      : null,
    bets: listOf(receipt.bets).map((bet) => ({
      id: numberOf(bet.id) ?? 0,
      statement: textOf(bet.statement) ?? "",
      state: textOf(bet.state) ?? "",
      finding: textOf(bet.finding),
    })),
    findingsReport: textOf(receipt.findings_report),
    cycles: listOf(receipt.cycles).map((cycle) => ({ number: numberOf(cycle.number) ?? 0, state: textOf(cycle.state) ?? "" })),
    finalScorecard: readScorecard(receipt.final_scorecard),
  };
}
