/**
 * "What needs me" (HUM-10): the one selector every surface reads. The server's desk is the only
 * definition; this file only arranges it. The nav badge, Home's inbox, each project's header and
 * tab badge, the page title and the app icon badge all come from `summarize` over one desk list,
 * so no two of them can disagree (tests: summary.test.ts, NeedsYou.test.tsx).
 */
import type { Schemas } from "../api/client";

export type DeskEntry = Schemas["DeskEntry"];

export type Urgency = "overdue" | "today" | "soon" | "later" | "none";

export interface NeedsSummary {
  entries: DeskEntry[];
  count: number;
  byProject: Map<string, DeskEntry[]>;
}

export function summarize(entries: readonly DeskEntry[]): NeedsSummary {
  const sorted = [...entries].sort(byPriority);
  const byProject = new Map<string, DeskEntry[]>();
  for (const entry of sorted) {
    byProject.set(entry.project_id, [...(byProject.get(entry.project_id) ?? []), entry]);
  }
  return { entries: sorted, count: sorted.length, byProject };
}

export function countFor(summary: NeedsSummary, projectId: string): number {
  return summary.byProject.get(projectId)?.length ?? 0;
}

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

/** How soon an entry falls due. Entries with no deadline come last. */
export function urgencyOf(entry: Pick<DeskEntry, "deadline">, now: number = Date.now()): Urgency {
  if (!entry.deadline) return "none";
  const left = new Date(entry.deadline).getTime() - now;
  if (Number.isNaN(left)) return "none";
  if (left <= 0) return "overdue";
  if (left <= DAY) return "today";
  if (left <= 3 * DAY) return "soon";
  return "later";
}

/** Soonest deadline first; items with no deadline after them, oldest first by id. */
export function byPriority(left: DeskEntry, right: DeskEntry): number {
  const a = left.deadline ? new Date(left.deadline).getTime() : Number.POSITIVE_INFINITY;
  const b = right.deadline ? new Date(right.deadline).getTime() : Number.POSITIVE_INFINITY;
  if (a !== b) return a - b;
  return (left.item?.id ?? 0) - (right.item?.id ?? 0);
}

/** The page title with the count in front, as mail apps do: "(2) Home · Nightsquad". */
export function titled(base: string, count: number): string {
  return count > 0 ? `(${count}) ${base}` : base;
}
