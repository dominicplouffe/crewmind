/**
 * The crew in plain words: who each agent is, what it is doing, what it has used (CHAT-12, CHAT-18,
 * EXE-4). Pure functions over what the server sends; presentation only, no rule lives here.
 */
import type { Header, Schemas, Seat } from "../api/client";
import { fromNow, tokens as tokenWords } from "../lib/humanize";
import { crew, runWords } from "../strings.crew";

export type Run = Schemas["RunItem"];
export type CrewStatus = "working" | "waiting" | "blocked" | "idle";

export interface CrewMember {
  name: string;
  role: string;
  team: string | null;
  lead: boolean;
  kind: string;
  state: string;
  status: CrewStatus;
  /** One plain sentence: what it is doing now. */
  now: string;
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
const STATUS_ORDER: Record<CrewStatus, number> = { working: 0, waiting: 1, blocked: 2, idle: 3 };

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

export function crewMembers(
  roster: { seats: readonly Seat[] } | null | undefined,
  header: Header | null | undefined,
  runs: readonly Run[],
  now: number = Date.now(),
): CrewMember[] {
  const bySeat = new Map<string, Run[]>();
  for (const run of runs) {
    const list = bySeat.get(run.seat) ?? [];
    list.push(run);
    bySeat.set(run.seat, list);
  }
  return (roster?.seats ?? []).map((seat) => {
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
    let sentence: string;
    if (live || liveRun) {
      status = "working";
      sentence = live ? doingSentence(live.doing, live.run_kind) : doingSentence("thinking", liveRun?.kind ?? "work");
    } else if (stoodDown) {
      status = "idle";
      sentence = crew.now.stoodDown;
    } else if (paused) {
      status = "blocked";
      sentence = crew.now.paused(seat.pause_reason);
    } else if (queued.length > 0) {
      status = "waiting";
      sentence = crew.now.queued(reasonWords(queued.flatMap((run) => run.reasons)));
    } else {
      status = "idle";
      sentence = lastActive ? crew.now.idleSince(fromNow(lastActive, now)) : crew.now.neverRan;
    }

    return {
      name: seat.name,
      role: seat.role,
      team: seat.team,
      lead: seat.lead,
      kind: seat.kind,
      state: seat.state,
      status,
      now: sentence,
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
  return STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.name.localeCompare(b.name, undefined, { numeric: true });
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

export interface StatusCounts {
  working: number;
  waiting: number;
  blocked: number;
  idle: number;
}

export function statusCounts(members: readonly CrewMember[]): StatusCounts {
  const counts: StatusCounts = { working: 0, waiting: 0, blocked: 0, idle: 0 };
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

/** One run as a sentence; the raw kind, state and reasons are kept for a "technical details" fold. */
export function runSentence(run: Run, now: number = Date.now()): RunSentence {
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
  const text = `${run.seat} ${action}, ${when}${tokens ? ` · ${tokens}` : ""}`;
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
