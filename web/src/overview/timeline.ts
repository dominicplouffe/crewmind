/**
 * The project's story from the activity feed (CHAT-19, P18): only what a chairman cares about,
 * named rather than numbered, grouped by day. A task done carries its title, a file its name, a
 * requirement its text and a decision its question; run bookkeeping, settings, directives, chat
 * sessions and other internals are left out.
 *
 * The feed sends one plain line per event with its type. Until it also sends the subject and the
 * states, the subject id and the new state are read from that line; a line that does not parse is
 * left out rather than shown with a raw id. Display only: nothing here decides anything.
 */
import type { Artifact, Schemas, Task } from "../api/client";
import { fromNow } from "../lib/humanize";
import { story, type Part } from "../strings.overview";

type FeedItem = Schemas["FeedItem"];
type Item = Pick<Schemas["ItemView"], "id" | "kind" | "title" | "outcome" | "fields">;
type Requirement = Pick<Schemas["RequirementItem"], "id" | "text">;

export type StoryKind =
  | "project"
  | "finished"
  | "blocked"
  | "delivered"
  | "updated"
  | "proposed"
  | "accepted"
  | "met"
  | "cut"
  | "declined"
  | "hired"
  | "asked"
  | "decided"
  | "hold"
  | "budget";

export interface Who {
  name: string;
  kind: "agent" | "person";
}

export interface StoryEntry {
  id: number;
  at: string;
  /** Relative today ("12 minutes ago"), a clock time on earlier days. */
  when: string;
  kind: StoryKind;
  who: Who | null;
  parts: Part[];
  /** The names behind a grouped line ("Maya delivered 2 files"), for a short list under it. */
  details: string[];
}

export interface StoryDay {
  key: string;
  label: string;
  entries: StoryEntry[];
}

export interface StorySources {
  feed: readonly FeedItem[];
  tasks: readonly Pick<Task, "id" | "title" | "claimant">[];
  requirements: readonly Requirement[];
  items: readonly Item[];
  files: readonly Pick<Artifact, "name" | "kind">[];
  /** The signed-in person's id, so their own actions read "You". */
  me: string | null;
}

/** One event before grouping. `subject` is what a grouped line lists. */
interface Raw {
  id: number;
  at: string;
  time: number;
  kind: StoryKind;
  who: Who | null;
  subject: string;
  /** Lines with the same key next to each other within the window become one. */
  groupKey: string | null;
  single: Part[];
}

/** Events closer than this, of one kind and by one actor, read as one line. */
const GROUP_WINDOW_MS = 30 * 60_000;
const DETAILS_SHOWN = 3;

const STATE_LINE = /^.+? (\d+) is now (.+)\.$/;
const SAVED_LINE = /^(.+) saved version (\d+) of (.+)\.$/;
const HIRED_LINE = /^Team (.+) was hired \((\d+) x (.+)\)\.$/;
const PROJECT_LINE = /^The project went from (.+) to (.+)\.$/;
/** Decision kinds already told by their own events (a proposed requirement). */
const TOLD_ELSEWHERE = new Set(["proposed scope"]);

interface Context {
  who(actor: string): Who | null;
  task: Map<number, { title: string; claimant: string | null }>;
  requirement: Map<number, string>;
  item: Map<number, Item>;
  fileKind: Map<string, string>;
}

/** Learns which seat an actor id is from lines that name it: a saved file, a claimed task. */
function actorNames(sources: StorySources): Map<string, string> {
  const names = new Map<string, string>();
  const claimant = new Map(sources.tasks.map((task) => [task.id, task.claimant]));
  for (const item of sources.feed) {
    if (names.has(item.actor)) continue;
    if (item.type === "artifact.version_added") {
      const author = SAVED_LINE.exec(item.text)?.[1];
      if (author) names.set(item.actor, author);
    } else if (item.type === "task.state_changed") {
      const match = STATE_LINE.exec(item.text);
      const seat = match && match[2] === "claimed" ? claimant.get(Number(match[1])) : null;
      if (seat) names.set(item.actor, seat);
    }
  }
  return names;
}

function itemTitle(item: Item): string {
  const question = item.fields?.["question"];
  return item.kind === "question" && typeof question === "string" && question.trim() ? question.trim() : item.title;
}

type Rule = (item: FeedItem, context: Context) => Omit<Raw, "id" | "at" | "time"> | null;

function stateOf(item: FeedItem): { id: number; state: string } | null {
  const match = STATE_LINE.exec(item.text);
  return match ? { id: Number(match[1]), state: match[2] ?? "" } : null;
}

const timeline = story.timeline;

const RULES: Record<string, Rule> = {
  "project.created": (item, context) => {
    const who = context.who(item.actor);
    return { kind: "project", who, subject: "", groupKey: null, single: timeline.project.created(who?.name ?? null) };
  },
  "project.state_changed": (item, context) => {
    const match = PROJECT_LINE.exec(item.text);
    if (!match) return null;
    const [, from = "", to = ""] = match;
    const who = context.who(item.actor);
    let single: Part[];
    if (to === "running") single = from === "draft" ? timeline.project.started(who?.name ?? null) : [timeline.project.resumed];
    else if (to === "held" || to === "paused" || to === "ready" || to === "completed" || to === "stopped") single = [timeline.project[to]];
    else single = [timeline.project.other(to)];
    return { kind: "project", who: to === "running" && from === "draft" ? who : null, subject: "", groupKey: null, single };
  },
  "project.hold_added": (item) => ({ kind: "hold", who: null, subject: "", groupKey: null, single: [item.text] }),
  "project.hold_lifted": (item) => ({ kind: "hold", who: null, subject: "", groupKey: null, single: [item.text] }),
  "budget.threshold_reached": (item) => ({ kind: "budget", who: null, subject: "", groupKey: null, single: [item.text] }),
  "team.hired": (item, context) => {
    const team = HIRED_LINE.exec(item.text)?.[1];
    if (!team) return null;
    const who = context.who(item.actor);
    return { kind: "hired", who, subject: team, groupKey: `hired:${who?.name ?? ""}`, single: timeline.hired(who?.name ?? null, [team]) };
  },
  "artifact.version_added": (item, context) => {
    const match = SAVED_LINE.exec(item.text);
    if (!match) return null;
    const [, author = "", version = "1", name = ""] = match;
    const kind = context.fileKind.get(name);
    if (kind !== undefined && kind !== "deliverable") return null;
    const who = context.who(item.actor) ?? (author ? { name: author, kind: "agent" as const } : null);
    const update = Number(version) > 1;
    return {
      kind: update ? "updated" : "delivered",
      who,
      subject: name,
      groupKey: `${update ? "updated" : "delivered"}:${who?.name ?? ""}`,
      single: timeline.delivered(who?.name ?? null, [name], update),
    };
  },
  "task.state_changed": (item, context) => {
    const change = stateOf(item);
    const task = change ? context.task.get(change.id) : undefined;
    if (!change || !task) return null;
    if (change.state === "done") {
      const who = task.claimant ? { name: task.claimant, kind: "agent" as const } : null;
      return { kind: "finished", who, subject: task.title, groupKey: `finished:${who?.name ?? ""}`, single: timeline.finished(who?.name ?? null, [task.title]) };
    }
    if (change.state === "blocked") {
      const who = context.who(item.actor);
      return { kind: "blocked", who, subject: task.title, groupKey: `blocked:${who?.name ?? ""}`, single: timeline.blocked(who?.name ?? null, [task.title]) };
    }
    return null;
  },
  "requirement.state_changed": (item, context) => {
    const change = stateOf(item);
    const text = change ? context.requirement.get(change.id) : undefined;
    if (!change || !text) return null;
    const who = context.who(item.actor);
    const name = who?.name ?? null;
    switch (change.state) {
      case "proposed":
        return { kind: "proposed", who, subject: text, groupKey: `proposed:${name ?? ""}`, single: timeline.proposed(name, [text]) };
      case "accepted":
        return { kind: "accepted", who, subject: text, groupKey: `accepted:${name ?? ""}`, single: timeline.accepted(name, [text]) };
      case "met":
        return { kind: "met", who: null, subject: text, groupKey: "met", single: timeline.met([text]) };
      case "cut":
        return { kind: "cut", who: null, subject: text, groupKey: "cut", single: timeline.cut([text]) };
      case "declined":
        return { kind: "declined", who: null, subject: text, groupKey: "declined", single: timeline.declined([text]) };
      default:
        return null;
    }
  },
  "item.state_changed": (item, context) => {
    const change = stateOf(item);
    const found = change ? context.item.get(change.id) : undefined;
    if (!change || !found || TOLD_ELSEWHERE.has(found.kind)) return null;
    const title = itemTitle(found);
    const who = context.who(item.actor);
    if (change.state === "open") {
      const single =
        found.kind === "question"
          ? timeline.asked(who?.name ?? null, title)
          : found.kind.startsWith("approval")
            ? timeline.approval(who?.name ?? null, title)
            : timeline.waiting(title);
      return { kind: "asked", who: found.kind === "question" || found.kind.startsWith("approval") ? who : null, subject: title, groupKey: null, single };
    }
    if (change.state === "decided") {
      return { kind: "decided", who, subject: title, groupKey: null, single: timeline.decided(who?.name ?? null, title, found.outcome) };
    }
    if (change.state === "defaulted") {
      return { kind: "decided", who: null, subject: title, groupKey: null, single: timeline.defaulted(title, found.outcome) };
    }
    return null;
  },
};

/** The parts of a grouped line, by kind. */
function groupParts(kind: StoryKind, who: string | null, subjects: string[]): Part[] {
  switch (kind) {
    case "finished":
      return timeline.finished(who, subjects);
    case "blocked":
      return timeline.blocked(who, subjects);
    case "delivered":
    case "updated":
      return timeline.delivered(who, subjects, kind === "updated");
    case "proposed":
      return timeline.proposed(who, subjects);
    case "accepted":
      return timeline.accepted(who, subjects);
    case "met":
      return timeline.met(subjects);
    case "cut":
      return timeline.cut(subjects);
    case "declined":
      return timeline.declined(subjects);
    case "hired":
      return timeline.hired(who, subjects);
    default:
      return [];
  }
}

function dayKey(time: number): string {
  const date = new Date(time);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" });
const clockFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

function dayLabel(time: number, now: number): string {
  if (dayKey(time) === dayKey(now)) return timeline.today;
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (dayKey(time) === dayKey(yesterday.getTime())) return timeline.yesterday;
  return dayFormat.format(time);
}

/** The newest `limit` story lines, newest first, grouped by day. */
export function storyOf(sources: StorySources, limit: number, now: number = Date.now()): StoryDay[] {
  const names = actorNames(sources);
  const context: Context = {
    who(actor) {
      if (sources.me && actor === sources.me) return { name: timeline.you, kind: "person" };
      const name = names.get(actor);
      return name ? { name, kind: "agent" } : null;
    },
    task: new Map(sources.tasks.map((task) => [task.id, { title: task.title, claimant: task.claimant }])),
    requirement: new Map(sources.requirements.map((requirement) => [requirement.id, requirement.text])),
    item: new Map(sources.items.map((item) => [item.id, item])),
    fileKind: new Map(sources.files.map((file) => [file.name, file.kind])),
  };
  const started = sources.feed.some((item) => item.type === "project.state_changed");

  const raws: Raw[] = [];
  for (const item of sources.feed) {
    if (item.type === "project.created" && started) continue;
    const rule = RULES[item.type];
    const made = rule?.(item, context);
    const time = Date.parse(item.at);
    if (made && !Number.isNaN(time)) raws.push({ ...made, id: item.id, at: item.at, time });
  }
  raws.sort((a, b) => b.time - a.time || b.id - a.id);

  // Neighbours of one kind by one actor, within the window and on one day, read as one line.
  const groups: { first: Raw; subjects: string[]; last: number }[] = [];
  for (const raw of raws) {
    const open = groups[groups.length - 1];
    if (
      open &&
      raw.groupKey !== null &&
      open.first.groupKey === raw.groupKey &&
      open.last - raw.time <= GROUP_WINDOW_MS &&
      dayKey(open.last) === dayKey(raw.time)
    ) {
      if (!open.subjects.includes(raw.subject)) open.subjects.push(raw.subject);
      open.last = raw.time;
      continue;
    }
    if (groups.length >= limit) break;
    groups.push({ first: raw, subjects: [raw.subject], last: raw.time });
  }

  const days: StoryDay[] = [];
  for (const { first, subjects } of groups) {
    // Listed oldest first, the order they happened in.
    const ordered = subjects.slice().reverse();
    const grouped = ordered.length > 1;
    const entry: StoryEntry = {
      id: first.id,
      at: first.at,
      when: dayKey(first.time) === dayKey(now) ? fromNow(first.at, now) : clockFormat.format(first.time),
      kind: first.kind,
      who: first.who,
      parts: grouped ? groupParts(first.kind, first.who?.name ?? null, ordered) : first.single,
      details: grouped ? shortList(ordered) : [],
    };
    const key = dayKey(first.time);
    const day = days[days.length - 1];
    if (day && day.key === key) day.entries.push(entry);
    else days.push({ key, label: dayLabel(first.time, now), entries: [entry] });
  }
  return days;
}

function shortList(names: string[]): string[] {
  if (names.length <= DETAILS_SHOWN + 1) return names;
  return [...names.slice(0, DETAILS_SHOWN), timeline.andMore(names.length - DETAILS_SHOWN)];
}
