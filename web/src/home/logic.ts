/**
 * How Home lays out what waits on the person (HUM-10): the desk's entries grouped by how soon they
 * fall due, and the one sentence that answers "what needs me". Presentation only: the entries and
 * their deadlines are the server's; this only sorts them into groups and words.
 */
import { fromNow } from "../lib/humanize";
import { byPriority, type DeskEntry } from "../needs/summary";
import { home } from "../strings.shell";

export type InboxGroupKey = "overdue" | "today" | "week" | "later";

export interface InboxGroup {
  key: InboxGroupKey;
  entries: DeskEntry[];
}

const DAY_MS = 24 * 3600 * 1000;
const WEEK_DAYS = 7;
const ORDER: InboxGroupKey[] = ["overdue", "today", "week", "later"];

/** Which group an entry falls in. "Today" is the next 24 hours, as the card's "Due today" says. */
export function groupOf(entry: Pick<DeskEntry, "deadline">, now: number = Date.now()): InboxGroupKey {
  if (!entry.deadline) return "later";
  const left = new Date(entry.deadline).getTime() - now;
  if (Number.isNaN(left)) return "later";
  if (left <= 0) return "overdue";
  if (left <= DAY_MS) return "today";
  if (left <= WEEK_DAYS * DAY_MS) return "week";
  return "later";
}

/** The entries in groups, soonest first; empty groups are left out. */
export function inboxGroups(entries: readonly DeskEntry[], now: number = Date.now()): InboxGroup[] {
  const sorted = [...entries].sort(byPriority);
  return ORDER.map((key) => ({ key, entries: sorted.filter((entry) => groupOf(entry, now) === key) })).filter(
    (group) => group.entries.length > 0,
  );
}

/** "3 decisions wait on you, the soonest in 24 hours." or that nothing does. */
export function summaryLine(entries: readonly DeskEntry[], projects: number, now: number = Date.now()): string {
  if (entries.length === 0) return home.summaryNone;
  const overdue = entries.filter((entry) => groupOf(entry, now) === "overdue").length;
  const dated = entries.filter((entry) => entry.deadline).sort(byPriority);
  const first = dated[0]?.deadline ?? null;
  const soon = overdue > 0 ? home.overdue(overdue) : first ? home.soonest(fromNow(first, now)) : null;
  return home.summary(entries.length, projects, soon);
}

/** Accepted scope, and how much of it is met. Proposed, cut and declined requirements are not scope. */
const SCOPE = new Set(["accepted", "in progress", "checking", "met"]);

export function requirementProgress(requirements: readonly { state: string }[] | undefined): { met: number; total: number } {
  const scope = (requirements ?? []).filter((requirement) => SCOPE.has(requirement.state));
  return { met: scope.filter((requirement) => requirement.state === "met").length, total: scope.length };
}
