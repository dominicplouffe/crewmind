/**
 * How a decision card words its deadline and who is asking (HUM-1, HUM-2). Presentation only: the
 * deadline, the default outcome and the filer come from the server; this only puts them into words.
 */
import { fromNow } from "../lib/humanize";
import { urgencyOf, type Urgency } from "../needs/summary";
import type { NameOf } from "../crew/names";
import { t } from "../strings";

/** The CEO's seat name: every project has exactly one (EXE-1). */
const CEO_SEAT = "CEO";

const WEEK_MS = 6 * 24 * 3600 * 1000;

/** "Tue 3 PM", "Tue 3:30 PM", or "Tue 2 Dec, 3 PM" when it is more than a few days away. */
export function shortWhen(iso: string, now: number = Date.now()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const time = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: date.getMinutes() === 0 ? undefined : "2-digit",
  }).format(date);
  const far = Math.abs(date.getTime() - now) > WEEK_MS;
  const day = new Intl.DateTimeFormat(
    undefined,
    far ? { weekday: "short", day: "numeric", month: "short" } : { weekday: "short" },
  ).format(date);
  return far ? `${day}, ${time}` : `${day} ${time}`;
}

export interface DeadlineWords {
  /** "Decide by Tue 3 PM · in 2 days", or that it has no deadline. */
  line: string;
  urgency: Urgency;
  /** "Overdue", "Due today", "Due soon", or empty when it is not pressing. */
  badge: string;
  /** "If you do nothing: it is declined." when the server names a default. */
  ifNothing: string | null;
}

export function deadlineWords(
  deadline: string | null | undefined,
  defaultOutcome: string | null | undefined,
  now: number = Date.now(),
): DeadlineWords {
  const words = t.decisions.card.when;
  const urgency = urgencyOf({ deadline: deadline ?? null }, now);
  const given = defaultOutcome?.trim();
  const outcome = given ? (t.decisions.card.defaults[given] ?? given) : null;
  let line: string = words.noDeadline;
  if (deadline) {
    const when = shortWhen(deadline, now);
    const relative = fromNow(deadline, now);
    line = urgency === "overdue" ? words.overdue(when, relative) : words.decideBy(when, relative);
  }
  return { line, urgency, badge: words.urgency[urgency] ?? "", ifNothing: outcome ? words.ifNothing(outcome) : null };
}

/** Kinds the server's registry says the CEO files. Other agent-filed kinds come from any agent. */
const CEO_KINDS = new Set([
  "proposed scope",
  "proposed commitment",
  "reserve draw",
  "approval: capacity",
  "approval: spend",
  "approval: legal",
  "question",
  "heads-up",
]);

export interface Asker {
  /** The name for the avatar, or null for crewmind itself. */
  name: string | null;
  /** The asking agent's seat, for the avatar's colour, when known. */
  seat?: string;
  line: string;
  /** Who, in a word: "CEO", "An agent", "crewmind", or the seat's name. */
  who: string;
}

/** An agent by the name it goes by and its role, when the project's roster is known (EXE-18). */
function named(seat: string, nameOf?: NameOf): Asker {
  const words = t.decisions.card.askedBy;
  const agent = nameOf?.(seat);
  if (!agent?.role || agent.name === agent.role) return { name: agent?.name ?? seat, seat, line: words.named(agent?.name ?? seat), who: agent?.name ?? seat };
  return { name: agent.name, seat, line: words.namedRole(agent.name, agent.role), who: t.decisions.compact.who.namedRole(agent.name, agent.role) };
}

/**
 * Who is asking, from the item's filer ("agent", "platform", or a seat's name) and its kind.
 * `nameOf` gives an agent's name and role inside a project; without it the role or seat is shown.
 */
export function askerOf(filedBy: string, kind: string, nameOf?: NameOf): Asker {
  const words = t.decisions.card.askedBy;
  const who = t.decisions.compact.who;
  if (filedBy === "platform" || filedBy === "") return { name: null, line: words.platform, who: who.platform };
  if (filedBy === "agent" || filedBy === "ceo") {
    if (!(CEO_KINDS.has(kind) || filedBy === "ceo")) return { name: "Agent", line: words.agent, who: who.agent };
    const ceo = nameOf?.(CEO_SEAT);
    return ceo && ceo.name !== CEO_SEAT ? named(CEO_SEAT, nameOf) : { name: "CEO", seat: CEO_SEAT, line: words.ceo, who: who.ceo };
  }
  return named(filedBy, nameOf);
}

/** The kind of decision in plain words. */
export function kindLabel(kind: string): string {
  return t.decisions.kinds[kind] ?? kind.charAt(0).toUpperCase() + kind.slice(1);
}
