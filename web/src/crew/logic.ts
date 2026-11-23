/**
 * The crew in plain words: who each agent is, what it is doing, what it has used (CHAT-12, CHAT-18,
 * EXE-4). Pure functions over what the server sends; presentation only, no rule lives here.
 */
import type { Header, Schemas, Seat } from "../api/client";
import { fromNow, tokens as tokenWords } from "../lib/humanize";
import { crew, runWords } from "../strings.crew";
import { roleLabel } from "./names";

export type Run = Schemas["RunItem"];
/**
 * What an agent is doing, from the server's runs and tasks: a live run (working), a claimed task
 * between runs (holding), its finished task waiting on a review or check (review), a queued run
 * (waiting), a paused seat or a blocked task (blocked), or nothing (idle).
 */
export type CrewStatus = "working" | "holding" | "review" | "waiting" | "blocked" | "idle";

/** The parts of a task the crew view reads. */
export interface CrewTask {
  id: number;
  title: string;
  state: string;
  claimant: string | null;
  team: string | null;
  reason: string | null;
}

export interface CrewMember {
  /** The seat name: the identity runs, tasks and chat authors use. */
  name: string;
  /** The name it goes by, shown first: "Maya" (EXE-18). */
  displayName: string;
  /** The role as the library names it: "CEO / Project Manager". */
  role: string;
  /** The role, short, shown under the name: "CEO". */
  roleLabel: string;
  team: string | null;
  lead: boolean;
  kind: string;
  state: string;
  status: CrewStatus;
  /** The status in one word or two: "Working", "Blocked", "Paused". */
  label: string;
  /** One plain sentence: what it is doing now. */
  now: string;
  /** What a live run is doing when the sentence names a task: "Using web search". */
  doing: string | null;
  /** The task the sentence is about, if any. */
  task: { id: number; title: string } | null;
  /** Why a task is blocked, as the agent wrote it (untrusted: shown as plain text). */
  reason: string | null;
  tokens: number;
  runs: number;
  /** When it last did anything, as an ISO time; null if it never ran. */
  lastActive: string | null;
  pauseReason: string | null;
  listeningScore: number | null;
  corrections: number;
  replies: number;
}

const LIVE = new Set(["leased", "running"]);
const STATUS_ORDER: Record<CrewStatus, number> = { blocked: 0, working: 1, holding: 2, review: 3, waiting: 4, idle: 5 };
/** Task states in which a finished piece of work waits on someone else's check. */
const AWAITING = new Set(["review", "checking"]);

/** The latest time a run shows any sign of life. */
export function runTime(run: Run): string {
  return run.ended_at ?? run.started_at ?? run.leased_at ?? run.queued_at;
}

function later(a: string | null, b: string | null): string | null {
  if (!a) return b;
  if (!b) return a;
  return Date.parse(a) >= Date.parse(b) ? a : b;
}

/** "using web_search" → "Using web search"; "thinking" in chat → "Writing a reply in chat". */
export function doingSentence(doing: string, runKind: string): string {
  const tool = /^using (.+)$/.exec(doing)?.[1];
  const words = tool ? crew.now.tool(tool.replace(/[_-]+/g, " ")) : doing;
  if (runKind === "chat") return doing === "thinking" ? crew.now.chatThinking : crew.now.chatDoing(words);
  if (runKind === "check") return crew.now.checkDoing(words);
  return crew.now.doing(words);
}

/** What a run was woken for, in words: "a directive", "your message". */
export function reasonWords(reasons: readonly string[]): string {
  const words = reasons.map((reason) => {
    const notice = /^notice: (.+)$/.exec(reason)?.[1];
    if (notice) return runWords.notices[notice] ?? runWords.notice(notice);
    if (/^message \d+ from a person$/.test(reason)) return runWords.yourMessage;
    return runWords.reasons[reason] ?? reason;
  });
  const unique = [...new Set(words)];
  return unique.length ? runWords.and(unique) : runWords.something;
}

/**
 * The seat a blocked task belongs to. The server clears the claimant when a task is blocked
 * (WRK-14), so a blocked task without one is shown on its team's lead, or on the team's only
 * member. Null when neither is known: the task then shows on the board only.
 */
export function blockedTaskHolder(task: CrewTask, seats: readonly Seat[]): string | null {
  if (task.claimant) return task.claimant;
  if (!task.team) return null;
  const team = seats.filter((seat) => seat.team === task.team && seat.state !== "stood down" && seat.kind !== "ceo");
  const lead = team.find((seat) => seat.lead || seat.kind === "lead");
  if (lead) return lead.name;
  return team.length === 1 ? (team[0]?.name ?? null) : null;
}

function quoteList(tasks: readonly CrewTask[]): string {
  const [first] = tasks;
  if (!first) return "";
  return tasks.length === 1 ? crew.now.task(first.title) : crew.now.taskAndMore(first.title, tasks.length - 1);
}

export function crewMembers(
  roster: { seats: readonly Seat[] } | null | undefined,
  header: Header | null | undefined,
  runs: readonly Run[],
  tasks: readonly CrewTask[] = [],
  now: number = Date.now(),
): CrewMember[] {
  const bySeat = new Map<string, Run[]>();
  for (const run of runs) {
    const list = bySeat.get(run.seat) ?? [];
    list.push(run);
    bySeat.set(run.seat, list);
  }
  const seats = roster?.seats ?? [];
  const blockedBy = new Map<string, CrewTask[]>();
  for (const task of tasks) {
    if (task.state !== "blocked") continue;
    const holder = blockedTaskHolder(task, seats);
    if (holder) blockedBy.set(holder, [...(blockedBy.get(holder) ?? []), task]);
  }
  const toReview = tasks.filter((task) => task.state === "review");
  return seats.map((seat) => {
    const held = tasks.filter((task) => task.claimant === seat.name && task.state === "claimed");
    const awaiting = tasks.filter((task) => task.claimant === seat.name && AWAITING.has(task.state));
    const blocked = blockedBy.get(seat.name) ?? [];
    const own = bySeat.get(seat.name) ?? [];
    const live = header?.now.find((item) => item.seat === seat.name);
    const liveRun = own.find((run) => LIVE.has(run.state));
    const queued = own.filter((run) => run.state === "queued");
    const paused = seat.state === "paused" || Boolean(seat.pause_reason);
    const stoodDown = seat.state === "stood down";
    let lastActive: string | null = null;
    let used = 0;
    for (const run of own) {
      used += run.tokens_counted;
      if (run.state !== "queued" && run.state !== "dropped") lastActive = later(lastActive, runTime(run));
    }

    let status: CrewStatus;
    let label: string | null = null;
    let sentence: string;
    let doing: string | null = null;
    let about: CrewTask | null = null;
    let reason: string | null = null;
    const runKind = live?.run_kind ?? liveRun?.kind ?? "work";
    if (stoodDown) {
      status = "idle";
      sentence = crew.now.stoodDown;
    } else if (live || liveRun) {
      status = "working";
      const words = live ? doingSentence(live.doing, live.run_kind) : doingSentence("thinking", runKind);
      about = runKind === "work" ? (held[0] ?? null) : null;
      if (about) {
        sentence = crew.now.workingOn(quoteList(held));
        doing = words;
      } else {
        sentence = words;
      }
    } else if (paused) {
      status = "blocked";
      label = crew.status.paused ?? null;
      sentence = crew.now.paused(seat.pause_reason);
    } else if (blocked.length > 0) {
      status = "blocked";
      about = blocked[0] ?? null;
      sentence = crew.now.blocked(quoteList(blocked));
      reason = about?.reason ?? null;
    } else if (held.length > 0) {
      status = "holding";
      about = held[0] ?? null;
      sentence = crew.now.holding(quoteList(held));
    } else if (awaiting.length > 0) {
      status = "review";
      about = awaiting[0] ?? null;
      sentence = about?.state === "checking" ? crew.now.checking(quoteList(awaiting)) : crew.now.awaitingReview(quoteList(awaiting));
    } else if (seat.kind === "reviewer" && toReview.length > 0) {
      status = "holding";
      about = toReview[0] ?? null;
      sentence = crew.now.toReview(quoteList(toReview));
    } else if (queued.length > 0) {
      status = "waiting";
      sentence = crew.now.queued(reasonWords(queued.flatMap((run) => run.reasons)));
    } else {
      status = "idle";
      sentence = lastActive ? crew.now.idleSince(fromNow(lastActive, now)) : crew.now.neverRan;
    }

    return {
      name: seat.name,
      displayName: seat.display_name || seat.name,
      role: seat.role,
      roleLabel: roleLabel(seat),
      team: seat.team,
      lead: seat.lead,
      kind: seat.kind,
      state: seat.state,
      status,
      label: label ?? crew.status[status] ?? status,
      now: sentence,
      doing,
      task: about ? { id: about.id, title: about.title } : null,
      reason,
      tokens: used,
      runs: own.filter((run) => run.state !== "dropped").length,
      lastActive,
      pauseReason: seat.pause_reason,
      listeningScore: seat.listening_score ?? null,
      corrections: seat.corrections ?? 0,
      replies: seat.replies ?? 0,
    };
  });
}

/**
 * The role as given, without repeating the name: "CEO / Project Manager" on the seat named CEO
 * reads "Project Manager". Nothing is added; a role that is only the name is kept whole.
 */
export function roleLine(name: string, role: string): string {
  const parts = role
    .split(/\s*\/\s*/)
    .map((part) => part.trim())
    .filter(Boolean);
  const rest = parts.filter((part) => part.toLowerCase() !== name.trim().toLowerCase());
  return rest.length > 0 && rest.length < parts.length ? rest.join(" · ") : role;
}

/** Each member's share of the crew's tokens, 0 to 1. */
export function tokenShare(member: CrewMember, members: readonly CrewMember[]): number {
  const total = members.reduce((sum, one) => sum + one.tokens, 0);
  return total <= 0 ? 0 : member.tokens / total;
}

export interface TeamGroup {
  name: string;
  lead: CrewMember | null;
  members: CrewMember[];
}

export interface OrgTree {
  ceo: CrewMember | null;
  teams: TeamGroup[];
  /** Seats outside any team other than the CEO, such as the reviewer. */
  others: CrewMember[];
  /** Seats that were stood down. */
  former: CrewMember[];
}

function byStatusThenName(a: CrewMember, b: CrewMember): number {
  return (
    STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.displayName.localeCompare(b.displayName, undefined, { numeric: true })
  );
}

/** Chairman (drawn by the view) → CEO → teams, each lead first, then members; side seats apart. */
export function orgTree(members: readonly CrewMember[], teamNames: readonly string[] = []): OrgTree {
  const current = members.filter((member) => member.state !== "stood down");
  const former = members.filter((member) => member.state === "stood down");
  const ceo = current.find((member) => member.kind === "ceo") ?? null;
  const names = [...new Set([...teamNames, ...current.flatMap((member) => (member.team ? [member.team] : []))])];
  const teams = names
    .map((name) => {
      const inTeam = current.filter((member) => member.team === name && member !== ceo);
      const lead = inTeam.find((member) => member.lead || member.kind === "lead") ?? null;
      return { name, lead, members: inTeam.filter((member) => member !== lead).sort(byStatusThenName) };
    })
    .filter((team) => team.lead || team.members.length > 0);
  const others = current.filter((member) => member !== ceo && !member.team).sort(byStatusThenName);
  return { ceo, teams, others, former };
}

export type StatusCounts = Record<CrewStatus, number>;

/** The statuses in the order a summary lists them: what needs eyes first. */
export const SUMMARY_ORDER: readonly CrewStatus[] = ["working", "blocked", "holding", "review", "waiting", "idle"];

export function statusCounts(members: readonly CrewMember[]): StatusCounts {
  const counts: StatusCounts = { working: 0, holding: 0, review: 0, waiting: 0, blocked: 0, idle: 0 };
  for (const member of members) if (member.state !== "stood down") counts[member.status] += 1;
  return counts;
}

export interface RunSentence {
  seat: string;
  /** "worked on a directive" */
  action: string;
  /** "4 minutes ago", or "started 2 minutes ago" for a run still going. */
  when: string;
  tokens: string;
  /** "CEO worked on a directive, 4 minutes ago · 240 tokens" */
  text: string;
  tone: "success" | "accent" | "warning" | "danger" | "neutral";
  technical: { run: string; kind: string; state: string; reasons: string; detail: string | null; model: string | null; tokens: number };
}

const TONES: Record<string, RunSentence["tone"]> = {
  finished: "success",
  running: "accent",
  leased: "accent",
  queued: "neutral",
  dropped: "neutral",
  failed: "danger",
  terminated: "danger",
  killed: "warning",
  reaped: "warning",
};

/**
 * One run as a sentence; the raw kind, state and reasons are kept for a "technical details" fold.
 * `nameOf` gives the name the agent goes by (EXE-18); without it the seat name is used.
 */
export function runSentence(run: Run, now: number = Date.now(), nameOf?: (seat: string) => string): RunSentence {
  const what = reasonWords(run.reasons);
  let action: string;
  const work = runWords.work[run.state];
  if (run.kind === "work") action = work ? work(what) : runWords.other(run.kind, run.state);
  else if (run.kind === "chat") action = runWords.chat[run.state] ?? runWords.other(run.kind, run.state);
  else if (run.kind === "check") action = runWords.check[run.state] ?? runWords.other(run.kind, run.state);
  else action = runWords.other(run.kind, run.state);

  let when: string;
  if (run.state === "queued") when = runWords.queuedAt(fromNow(run.queued_at, now));
  else if (LIVE.has(run.state)) when = runWords.started(fromNow(run.started_at ?? run.leased_at ?? run.queued_at, now));
  else when = fromNow(runTime(run), now);

  const tokens = run.tokens_counted > 0 ? tokenWords(run.tokens_counted) : "";
  const text = `${nameOf ? nameOf(run.seat) : run.seat} ${action}, ${when}${tokens ? ` · ${tokens}` : ""}`;
  return {
    seat: run.seat,
    action,
    when,
    tokens,
    text,
    tone: TONES[run.state] ?? "neutral",
    technical: {
      run: run.run_id,
      kind: run.kind,
      state: run.state,
      reasons: run.reasons.join("; "),
      detail: run.end_detail,
      model: run.model ? `${run.model}${run.provider ? ` (${run.provider})` : ""}` : null,
      tokens: run.tokens_counted,
    },
  };
}

/** Newest first, by the time a run last showed life. */
export function recentRuns(runs: readonly Run[], seat?: string, limit = Infinity): Run[] {
  return runs
    .filter((run) => seat === undefined || run.seat === seat)
    .slice()
    .sort((a, b) => Date.parse(runTime(b)) - Date.parse(runTime(a)))
    .slice(0, limit);
}
