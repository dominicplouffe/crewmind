/**
 * The project at a glance in words (PLN-5, GOV-1, CHAT-19): progress through the requirements,
 * the projection, the budget pace and a short timeline. Display only; every number and state
 * comes from the server.
 */
import type { Schemas } from "../api/client";
import { duration, fromNow } from "../lib/humanize";
import { overview } from "../strings.crew";
import type { Segment } from "../ui/Progress";

type Requirement = Pick<Schemas["RequirementItem"], "state">;
type Pace = Schemas["PaceView"];
type FeedItem = Schemas["FeedItem"];

const SEGMENT_OF: Record<string, Segment["tone"]> = {
  proposed: "proposed",
  accepted: "todo",
  "in progress": "active",
  checking: "active",
  met: "done",
};

export interface Progress {
  segments: Segment[];
  counted: number;
  excluded: number;
  proposed: number;
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
  const segments: Segment[] = [
    { key: "done", label: overview.segments.done, value: counts.done, tone: "done" },
    { key: "active", label: overview.segments.active, value: counts.active, tone: "active" },
    { key: "todo", label: overview.segments.todo, value: counts.todo, tone: "todo" },
    { key: "proposed", label: overview.segments.proposed, value: counts.proposed, tone: "proposed" },
  ];
  return { segments, counted: counts.proposed + counts.todo + counts.active + counts.done, excluded, proposed: counts.proposed };
}

const dateFormat = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/** "Projected to finish in about 6 h (best case)." from the plan's pace. */
export function projectionSentence(pace: Pace, proposed: number, now: number = Date.now()): string {
  const waiting = proposed > 0 ? ` ${overview.projection.waitingOnYou(proposed)}` : "";
  if (pace.projection_kind === "nothing left") return `${overview.projection.nothingLeft}${waiting}`;
  if (pace.projection_kind === "unknown" || !pace.projected_at) return `${overview.projection.unknown}${waiting}`;
  const at = Date.parse(pace.projected_at);
  if (Number.isNaN(at)) return overview.projection.raw(pace.projection);
  const span = duration((at - now) / 1000);
  if (pace.projection_kind === "best case") return `${overview.projection.bestCase(span)}${waiting}`;
  return `${overview.projection.measured(span, dateFormat.format(at))}${waiting}`;
}

/** "20 h" or "3 days" of active work left at the measured pace. */
export function lastsFor(hours: number): string {
  return duration(hours * 3600);
}

/** Event types that are noise on a short timeline: run bookkeeping and setting echoes. */
const QUIET_TYPES = new Set(["run.state_changed", "setting.changed", "member.added"]);
const HEX_ID = /\s*\((?:project|person|seat|run) [0-9a-f]{32}\)/g;

export interface TimelineItem {
  id: number;
  at: string;
  when: string;
  text: string;
  type: string;
}

/** The newest lines worth reading, newest first, without raw ids. */
export function timelineOf(items: readonly FeedItem[], limit: number, now: number = Date.now()): TimelineItem[] {
  return items
    .filter((item) => !QUIET_TYPES.has(item.type))
    .slice()
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at) || b.id - a.id)
    .slice(0, limit)
    .map((item) => ({ id: item.id, at: item.at, when: fromNow(item.at, now), text: tidy(item.text), type: item.type }));
}

/** Drops raw ids from a server line and starts it with a capital. */
export function tidy(text: string): string {
  const clean = text.replace(HEX_ID, "").trim();
  return clean.charAt(0).toUpperCase() + clean.slice(1);
}
