/**
 * The project in words (PLN-5, GOV-1, CHAT-18, EXE-4): the headline sentence, progress through the
 * requirements, the projection and the budget pace. Display only; every number and state comes
 * from the server, and nothing here decides anything.
 */
import type { Schemas, Task } from "../api/client";
import { compactNumber, duration, share } from "../lib/humanize";
import { story } from "../strings.overview";
import type { Segment } from "../ui/Progress";

type Requirement = Pick<Schemas["RequirementItem"], "state">;
type Pace = Schemas["PaceView"];
type TaskLike = Pick<Task, "state" | "requirement_id" | "title" | "reason">;

const SEGMENT_OF: Record<string, Segment["tone"]> = {
  proposed: "proposed",
  accepted: "todo",
  "in progress": "active",
  checking: "active",
  met: "done",
};
/** Killed tasks are no longer work and are not counted. */
const NOT_COUNTED = new Set(["killed"]);
const FINISHED = new Set(["done"]);
/** Closed with no reviewer left: not open, and not counted as done either (P5). */
const CLOSED = new Set(["done", "closed unread"]);
/** Below this, a projected finish is shown as "minutes", not as a number of seconds. */
const SHORTEST_PROJECTION_S = 5 * 60;

export interface Progress {
  segments: Segment[];
  counted: number;
  excluded: number;
  proposed: number;
  met: number;
  active: number;
}

/** Proposed → accepted, not started → in progress (with checking) → met; cut and declined are left out. */
export function progressOf(requirements: readonly Requirement[]): Progress {
  const counts = { proposed: 0, todo: 0, active: 0, done: 0 };
  let excluded = 0;
  for (const requirement of requirements) {
    const tone = SEGMENT_OF[requirement.state];
    if (tone) counts[tone] += 1;
    else excluded += 1;
  }
  const words = story.progress.segments;
  const segments: Segment[] = [
    { key: "done", label: words.done, value: counts.done, tone: "done" },
    { key: "active", label: words.active, value: counts.active, tone: "active" },
    { key: "todo", label: words.todo, value: counts.todo, tone: "todo" },
    { key: "proposed", label: words.proposed, value: counts.proposed, tone: "proposed" },
  ];
  return {
    segments,
    counted: counts.proposed + counts.todo + counts.active + counts.done,
    excluded,
    proposed: counts.proposed,
    met: counts.done,
    active: counts.active,
  };
}

export interface TaskCount {
  done: number;
  total: number;
}

export function taskCount(tasks: readonly Pick<Task, "state">[]): TaskCount {
  const counted = tasks.filter((task) => !NOT_COUNTED.has(task.state));
  return { done: counted.filter((task) => FINISHED.has(task.state)).length, total: counted.length };
}

export interface RequirementRow {
  id: number;
  text: string;
  state: string;
  stateWord: string;
  tone: Segment["tone"];
  done: number;
  total: number;
}

/** One row per counted requirement, in the plan's order, with its tasks done out of all. */
export function requirementRows(
  requirements: readonly Pick<Schemas["RequirementItem"], "id" | "text" | "state">[],
  tasks: readonly TaskLike[],
): RequirementRow[] {
  return requirements
    .filter((requirement) => SEGMENT_OF[requirement.state] !== undefined)
    .map((requirement) => {
      const own = taskCount(tasks.filter((task) => task.requirement_id === requirement.id));
      return {
        id: requirement.id,
        text: requirement.text,
        state: requirement.state,
        stateWord: story.progress.states[requirement.state] ?? requirement.state,
        tone: SEGMENT_OF[requirement.state] ?? "todo",
        done: own.done,
        total: own.total,
      };
    });
}

export type HeadlineTone = "neutral" | "steady" | "attention" | "held" | "stopped" | "done";

export interface Headline {
  tone: HeadlineTone;
  lead: string;
  /** "3 of 4 requirements under way, 2 of 5 tasks done, 55% of the budget used." */
  facts: string;
  /** The first blocked task, when there is one; shown under the headline with its reason. */
  blocked: { title: string; reason: string | null; others: number } | null;
}

export interface HeadlineInput {
  state: string;
  holds: readonly { reason: string; lifts: string }[];
  atWall: boolean;
  requirements: readonly Requirement[];
  tasks: readonly TaskLike[];
  spent: number;
  wall: number;
}

/** The state of the project as one sentence a chairman can read at a glance. */
export function headlineOf(input: HeadlineInput): Headline {
  const words = story.headline;
  const progress = progressOf(input.requirements);
  const tasks = taskCount(input.tasks);
  const blockedTasks = input.tasks.filter((task) => task.state === "blocked");
  const open = input.tasks.filter((task) => !NOT_COUNTED.has(task.state) && !CLOSED.has(task.state));
  const firstBlocked = blockedTasks[0];
  const blocked = firstBlocked
    ? { title: firstBlocked.title, reason: firstBlocked.reason?.trim() || null, others: blockedTasks.length - 1 }
    : null;

  const clauses: string[] = [];
  if (progress.counted > 0) clauses.push(words.requirements(progress.met, progress.active, progress.counted));
  if (tasks.total > 0) clauses.push(words.tasks(tasks.done, tasks.total));
  if (input.wall > 0) clauses.push(words.budget(share(input.spent, input.wall)));
  const listed = clauses.length ? `${capital(clauses.join(", "))}.` : "";

  const hold = input.holds.find((line) => line.reason !== "chairman") ?? input.holds[0];
  const holdText = hold ? words.hold(words.holds[hold.reason] ?? hold.reason.replace(/_/g, " "), hold.lifts) : "";
  const lead = (key: string): string => words.lead[key] ?? key;

  switch (input.state) {
    case "draft":
      return { tone: "neutral", lead: lead("draft"), facts: words.draft, blocked: null };
    case "stopped":
      return { tone: "stopped", lead: lead("stopped"), facts: listed, blocked: null };
    case "completed":
      return { tone: "done", lead: lead("completed"), facts: listed, blocked: null };
    case "ready":
      return { tone: "done", lead: lead("ready"), facts: listed, blocked: null };
    case "held":
    case "paused":
      return { tone: "held", lead: lead(input.state), facts: [holdText, listed].filter(Boolean).join(" "), blocked };
  }
  if (input.atWall) return { tone: "stopped", lead: lead("paused"), facts: [story.budget.atWall, listed].join(" "), blocked };
  if (progress.counted === 0) return { tone: "neutral", lead: lead("starting"), facts: words.noRequirements, blocked: null };
  if (progress.met === progress.counted && open.length === 0) return { tone: "done", lead: lead("allMet"), facts: listed, blocked: null };
  if (open.length > 0 && open.every((task) => task.state === "blocked")) {
    return { tone: "attention", lead: lead("blocked"), facts: listed, blocked };
  }
  return { tone: blocked ? "attention" : "steady", lead: lead("steady"), facts: listed, blocked };
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const dateFormat = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/**
 * The projected finish in words, from the plan's pace. A projection only minutes away (as on a
 * fast mock server) is said as "minutes of running time", never as a count of seconds.
 */
export function projectionSentence(pace: Pace, proposed: number, now: number = Date.now()): string {
  const words = story.progress.projection;
  const waiting = proposed > 0 ? ` ${words.waitingOnYou(proposed)}` : "";
  if (pace.projection_kind === "nothing left") return `${words.nothingLeft}${waiting}`;
  if (pace.projection_kind === "unknown" || !pace.projected_at) return `${words.unknown}${waiting}`;
  const at = Date.parse(pace.projected_at);
  if (Number.isNaN(at)) return words.raw(pace.projection);
  const seconds = (at - now) / 1000;
  if (seconds < SHORTEST_PROJECTION_S) return `${words.soon}${waiting}`;
  const span = duration(seconds);
  if (pace.projection_kind === "best case") return `${words.bestCase(span)}${waiting}`;
  return `${words.measured(span, dateFormat.format(at))}${waiting}`;
}

/** "20 h" or "3 days" of active work left at the measured pace. */
export function lastsFor(hours: number): string {
  return duration(hours * 3600);
}

/** A measured rate to two significant figures: "about 950K", not "about 950.1K". */
export function roughly(value: number): number {
  if (value <= 0) return 0;
  const unit = 10 ** Math.max(0, Math.floor(Math.log10(value)) - 1);
  return Math.round(value / unit) * unit;
}

export interface BudgetWords {
  used: string;
  share: string;
  /** The pace in a sentence, or what is known when no pace is measured yet. */
  pace: string;
  /** A short form for the side rail. */
  paceShort: string | null;
}

export function budgetWords(budget: { spent: number; wall: number; remaining: number }, burnRate: number | null): BudgetWords {
  const words = story.budget;
  const used = words.used(compactNumber(budget.spent), compactNumber(budget.wall));
  const shareText = share(budget.spent, budget.wall);
  if (!burnRate || burnRate <= 0) return { used, share: shareText, pace: words.noPace, paceShort: null };
  const lasts = lastsFor(Math.max(0, budget.remaining) / burnRate);
  return {
    used,
    share: shareText,
    pace: words.pace(compactNumber(roughly(burnRate)), compactNumber(Math.max(0, budget.remaining)), lasts),
    paceShort: words.paceShort(lasts),
  };
}
