/**
 * Display helpers for decision items, the Desk and the agenda. No rules live here: which actions an
 * item offers, and whether one is allowed, is the server's answer. These only say what to ask the
 * person for before sending an action, and how to lay lists out.
 */
import type { Schemas } from "../api/client";
import { toMoment, wholeNumber } from "../panels/plan/logic";
import { t } from "../strings";

/** Two server schemas are called ItemView (decision items, and passages of a grilled document), so the generated name is the long one. */
export type Item = Schemas["ItemView"];
export type DeskEntry = Schemas["DeskEntry"];
export type AgendaLine = Schemas["AgendaLine"];

export type Need = "required" | "optional";

/** What to ask the person for before an action is sent. */
export interface ActionNeeds {
  amount?: Need;
  note?: Need;
  date?: Need;
  /** The answer to a question: one of its options, or the person's own words. */
  answer?: boolean;
  /** Ask "are you sure" first. */
  confirm: boolean;
}

const CONFIRM_FIRST = ["deny", "decline", "reject", "accept anyway"];

export function needsOf(kind: string, action: string): ActionNeeds {
  const confirm = CONFIRM_FIRST.includes(action);
  if (kind === "question" && action === "answer") return { answer: true, confirm };
  if (kind === "budget checkpoint" && action === "raise the budget") return { amount: "required", confirm };
  if (kind === "approval: capacity" && action === "approve") return { amount: "optional", confirm };
  if (kind === "proposed commitment" && action === "accept") return { date: "optional", confirm };
  if (kind === "verdict" && action === "reject") return { note: "required", confirm };
  return confirm ? { note: "optional", confirm } : { confirm };
}

/** Whether pressing the action's button opens a small form instead of sending it at once. */
export function asksFirst(needs: ActionNeeds): boolean {
  return needs.confirm || Boolean(needs.amount || needs.note || needs.date || needs.answer);
}

export interface ActionValues {
  amount?: string;
  note?: string;
  date?: string;
  option?: number | null;
}

type DecideBody = Schemas["crewmind__domain__decisions__operations__DecideInput"];

/**
 * The request for an action, or a sentence saying what is still missing. Only what the person
 * filled in is sent.
 */
export function decideBody(item: Item, action: string, values: ActionValues): DecideBody | string {
  const needs = needsOf(item.kind, action);
  const body: DecideBody = { project_id: item.project_id, item_id: item.id, action };
  const note = values.note?.trim() ?? "";
  if (note) body.note = note;
  if (needs.note === "required" && !note) return t.decisions.card.inputs.rejectNote;
  if (needs.amount) {
    const text = values.amount?.trim() ?? "";
    const amount = wholeNumber(text);
    if (amount !== null) body.amount = amount;
    else if (text || needs.amount === "required") return t.decisions.card.amountNeeded;
  }
  if (needs.date) {
    const date = toMoment(values.date ?? "");
    if (date) body.date = date;
  }
  if (needs.answer) {
    if (values.option) body.option = values.option;
    else if (!note) return t.decisions.question.needAnswer;
  }
  return body;
}

/** The server's rule (HUM-10): an item with no deadline comes back within this many days. */
export const SNOOZE_MOST_DAYS = 7;
/** "Until tomorrow" means this hour of the next morning, in the person's own time. */
const TOMORROW_HOUR = 9;
const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const THREE_DAYS = 3;

export type SnoozePresetId = "hour" | "tomorrow" | "threeDays";

export interface SnoozePreset {
  id: SnoozePresetId;
  until: Date;
  /** False when the time is past the latest the item can be set aside until. */
  allowed: boolean;
}

/** The latest moment an item can be set aside until: its deadline, or a week from now. */
export function snoozeLatest(now: Date, deadline: string | null | undefined): Date {
  const due = deadline ? new Date(deadline) : null;
  return due && !Number.isNaN(due.getTime()) ? due : new Date(now.getTime() + SNOOZE_MOST_DAYS * DAY_MS);
}

export function snoozePresets(now: Date, deadline: string | null | undefined): SnoozePreset[] {
  const latest = snoozeLatest(now, deadline).getTime();
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, TOMORROW_HOUR);
  const times: [SnoozePresetId, Date][] = [
    ["hour", new Date(now.getTime() + HOUR_MS)],
    ["tomorrow", tomorrow],
    ["threeDays", new Date(now.getTime() + THREE_DAYS * DAY_MS)],
  ];
  return times.map(([id, until]) => ({ id, until, allowed: until.getTime() <= latest }));
}

/** The deadline and what happens after it, in one plain sentence. */
export function deadlineText(
  deadline: string | null | undefined,
  defaultOutcome: string | null | undefined,
  formatWhen: (iso: string) => string,
): string {
  const words = t.decisions.card.deadline;
  const given = defaultOutcome?.trim();
  const outcome = given ? (t.decisions.card.defaults[given] ?? given) : given;
  if (deadline && outcome) return words.both(formatWhen(deadline), outcome);
  if (deadline) return words.dateOnly(formatWhen(deadline));
  if (outcome) return words.outcomeOnly(outcome);
  return words.none;
}

export interface DayGroup<T> {
  /** The local calendar day, as `2031-05-20`, for use as a key. */
  day: string;
  /** A moment in that day, to format as a heading. */
  date: Date;
  lines: T[];
}

function dayKey(date: Date): string {
  const two = (value: number): string => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`;
}

/** Groups dated lines by the viewer's own calendar day, earliest day first and in time order within a day. */
export function groupByDay<T extends { at: string }>(lines: T[]): DayGroup<T>[] {
  const sorted = [...lines].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const groups: DayGroup<T>[] = [];
  for (const line of sorted) {
    const date = new Date(line.at);
    const day = dayKey(date);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.lines.push(line);
    else groups.push({ day, date, lines: [line] });
  }
  return groups;
}

export interface ProjectGroup {
  projectId: string;
  name: string;
  entries: DeskEntry[];
}

/** Desk entries by project, in the order the server listed them. */
export function groupByProject(entries: DeskEntry[]): ProjectGroup[] {
  const groups = new Map<string, ProjectGroup>();
  for (const entry of entries) {
    const group = groups.get(entry.project_id) ?? { projectId: entry.project_id, name: entry.project_name, entries: [] };
    group.entries.push(entry);
    groups.set(entry.project_id, group);
  }
  return [...groups.values()];
}

/** The lists of a brief or a summary that hold something, in the given order, each line as text. */
export function filledSections(sections: unknown, order: readonly string[]): { name: string; lines: string[] }[] {
  if (typeof sections !== "object" || sections === null) return [];
  const source = sections as Record<string, unknown>;
  return order
    .map((name) => {
      const value = source[name];
      const lines = Array.isArray(value) ? value.map((line) => (typeof line === "string" ? line : JSON.stringify(line))) : [];
      return { name, lines };
    })
    .filter((section) => section.lines.length > 0);
}

export const BRIEF_SECTIONS = [
  "worth your eye",
  "what moved",
  "what the CEO handled itself",
  "what decided itself",
  "what happens next",
] as const;

export const AWAY_SECTIONS = ["what moved", "what decided itself", "what waits on you", "what happens next"] as const;

/** Items the chairman may give more time to (the server allows it for approvals and assists only). */
export function canExtend(item: Item): boolean {
  return item.actions.length > 0 && (item.kind.startsWith("approval:") || item.kind === "assist");
}

/** Typed readers for an item's `fields`, whose shape depends on its kind. */
export function textField(fields: Record<string, unknown>, name: string): string | null {
  const value = fields[name];
  return typeof value === "string" && value.trim() ? value : null;
}

export function numberField(fields: Record<string, unknown>, name: string): number | null {
  const value = fields[name];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function listField(fields: Record<string, unknown>, name: string): unknown[] {
  const value = fields[name];
  return Array.isArray(value) ? value : [];
}

export interface LeverUse {
  lever: string;
  reason: string;
}

/** The levers recorded on a status review, skipping anything that is not one. */
export function leversOf(fields: Record<string, unknown>, name: "levers" | "previous_levers"): LeverUse[] {
  return listField(fields, name).flatMap((entry) => {
    const use = entry as { lever?: unknown; reason?: unknown } | null;
    return typeof use?.lever === "string" ? [{ lever: use.lever, reason: typeof use.reason === "string" ? use.reason : "" }] : [];
  });
}
