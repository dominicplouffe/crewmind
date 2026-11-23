/** CHAT-12, CHAT-18, EXE-4: the crew's status, "now" sentences, usage and run sentences. */
import { describe, expect, it } from "vitest";
import type { Header, Seat } from "../api/client";
import {
  blockedTaskHolder,
  crewMembers,
  doingSentence,
  orgTree,
  reasonWords,
  recentRuns,
  roleLine,
  runSentence,
  statusCounts,
  tokenShare,
  type CrewTask,
  type Run,
} from "./logic";

const NOW = Date.parse("2026-11-22T12:00:00Z");
const ago = (minutes: number): string => new Date(NOW - minutes * 60_000).toISOString();

function seat(name: string, extra: Partial<Seat> = {}): Seat {
  return { name, kind: "worker", role: name, team: null, lead: false, state: "active", pause_reason: null, ...extra };
}

function run(seatName: string, extra: Partial<Run> = {}): Run {
  return {
    run_id: `${seatName}-${Math.random()}`,
    seat: seatName,
    kind: "work",
    state: "finished",
    attempt: 1,
    reasons: ["notice: directive issued"],
    model: "m",
    provider: "p",
    queued_at: ago(10),
    leased_at: ago(10),
    started_at: ago(10),
    ended_at: ago(9),
    end_detail: null,
    tokens_counted: 100,
    ...extra,
  };
}

function header(now: Header["now"]): Header {
  return { state: "running", now, next: [], waiting_on_you: 0, budget: "", budget_spent: 0, budget_wall: 1, holds: [], notes: [], unread: 0 };
}

describe("crewMembers status (CHAT-18, EXE-4)", () => {
  const cases: { title: string; seat: Seat; runs: Run[]; header: Header | null; status: string; now: string }[] = [
    {
      title: "working when the header lists it",
      seat: seat("CEO"),
      runs: [],
      header: header([{ seat: "CEO", run_kind: "work", doing: "using web_search" }]),
      status: "working",
      now: "Using web search",
    },
    {
      title: "working in chat reads as writing a reply",
      seat: seat("CEO"),
      runs: [],
      header: header([{ seat: "CEO", run_kind: "chat", doing: "thinking" }]),
      status: "working",
      now: "Writing a reply in chat",
    },
    {
      title: "blocked when the seat is paused, with its reason",
      seat: seat("writer-1", { state: "paused", pause_reason: "its model was retired" }),
      runs: [],
      header: header([]),
      status: "blocked",
      now: "Paused: its model was retired",
    },
    {
      title: "waiting when a run is queued",
      seat: seat("writer-1"),
      runs: [run("writer-1", { state: "queued", ended_at: null, started_at: null, leased_at: null, reasons: ["unread messages"] })],
      header: header([]),
      status: "waiting",
      now: "About to start: new messages from the crew",
    },
    {
      title: "idle since its last run",
      seat: seat("writer-1"),
      runs: [run("writer-1", { ended_at: ago(4) })],
      header: header([]),
      status: "idle",
      now: "Idle since 4 minutes ago",
    },
    {
      title: "idle and never ran",
      seat: seat("writer-1"),
      runs: [],
      header: null,
      status: "idle",
      now: "Has not run yet",
    },
    {
      title: "working from a live run when the header has not caught up",
      seat: seat("writer-1"),
      runs: [run("writer-1", { state: "running", ended_at: null })],
      header: header([]),
      status: "working",
      now: "Thinking",
    },
  ];
  it.each(cases)("$title", ({ seat: one, runs, header: head, status, now }) => {
    const [member] = crewMembers({ seats: [one] }, head, runs, [], NOW);
    expect(member?.status).toBe(status);
    expect(member?.now).toBe(now);
  });

  it("sums tokens and counts runs per seat, and keeps the latest activity", () => {
    const runs = [run("A", { tokens_counted: 120, ended_at: ago(30) }), run("A", { tokens_counted: 240, ended_at: ago(5) }), run("B")];
    const [a] = crewMembers({ seats: [seat("A")] }, null, runs, [], NOW);
    expect(a?.tokens).toBe(360);
    expect(a?.runs).toBe(2);
    expect(a?.lastActive).toBe(ago(5));
  });
});

function task(id: number, title: string, state: string, extra: Partial<CrewTask> = {}): CrewTask {
  return { id, title, state, claimant: null, team: null, reason: null, ...extra };
}

describe("crewMembers status from tasks (CHAT-18, EXE-4, WRK-14)", () => {
  const maya = seat("Maya", { team: "words", lead: true });
  const priya = seat("Priya", { team: "backend", lead: true });
  const reviewer = seat("Reviewer", { kind: "reviewer" });
  const idleRun = run("Maya", { ended_at: ago(4) });
  const cases: {
    title: string;
    seat: Seat;
    seats?: Seat[];
    tasks: CrewTask[];
    runs?: Run[];
    header?: Header | null;
    status: string;
    label: string;
    now: string;
    task?: number | null;
    reason?: string | null;
    doing?: string | null;
  }[] = [
    {
      title: "holding a claimed task with no live run",
      seat: maya,
      tasks: [task(2, "Write the FAQ", "claimed", { claimant: "Maya", team: "words" })],
      runs: [idleRun],
      status: "holding",
      label: "Assigned",
      now: "Holding “Write the FAQ”",
      task: 2,
    },
    {
      title: "working on its claimed task while a work run is live",
      seat: maya,
      tasks: [task(2, "Write the FAQ", "claimed", { claimant: "Maya" })],
      header: header([{ seat: "Maya", run_kind: "work", doing: "using write_file" }]),
      status: "working",
      label: "Working",
      now: "Working on “Write the FAQ”",
      doing: "Using write file",
      task: 2,
    },
    {
      title: "a live chat run is not the task",
      seat: maya,
      tasks: [task(2, "Write the FAQ", "claimed", { claimant: "Maya" })],
      header: header([{ seat: "Maya", run_kind: "chat", doing: "thinking" }]),
      status: "working",
      label: "Working",
      now: "Writing a reply in chat",
      task: null,
    },
    {
      title: "several claimed tasks are counted",
      seat: maya,
      tasks: [task(2, "Write the FAQ", "claimed", { claimant: "Maya" }), task(6, "Write the tagline", "claimed", { claimant: "Maya" })],
      status: "holding",
      label: "Assigned",
      now: "Holding “Write the FAQ” and 1 other task",
    },
    {
      title: "its task in review",
      seat: seat("Theo"),
      tasks: [task(3, "Build the pricing table", "review", { claimant: "Theo" })],
      status: "review",
      label: "Awaiting review",
      now: "Waiting for review of “Build the pricing table”",
      task: 3,
    },
    {
      title: "its task being checked",
      seat: seat("Theo"),
      tasks: [task(3, "Build the pricing table", "checking", { claimant: "Theo" })],
      status: "review",
      label: "Awaiting review",
      now: "Waiting for the check on “Build the pricing table”",
    },
    {
      title: "a blocked task it still holds, with the reason",
      seat: priya,
      tasks: [task(5, "Wire the sign-up form", "blocked", { claimant: "Priya", reason: "Waiting for the chairman." })],
      status: "blocked",
      label: "Blocked",
      now: "Blocked on “Wire the sign-up form”",
      reason: "Waiting for the chairman.",
      task: 5,
    },
    {
      title: "a blocked team task (no claimant) shows on the team's lead",
      seat: priya,
      tasks: [task(5, "Wire the sign-up form", "blocked", { team: "backend", reason: "Waiting for the chairman." })],
      status: "blocked",
      label: "Blocked",
      now: "Blocked on “Wire the sign-up form”",
      reason: "Waiting for the chairman.",
    },
    {
      title: "blocked outranks a task in review",
      seat: priya,
      tasks: [
        task(4, "Pick the email provider", "review", { claimant: "Priya" }),
        task(5, "Wire the sign-up form", "blocked", { team: "backend", reason: "Waiting." }),
      ],
      status: "blocked",
      label: "Blocked",
      now: "Blocked on “Wire the sign-up form”",
    },
    {
      title: "a paused seat reads Paused, before any task",
      seat: seat("Priya", { state: "paused", pause_reason: "its model was retired" }),
      tasks: [task(5, "Wire the sign-up form", "claimed", { claimant: "Priya" })],
      status: "blocked",
      label: "Paused",
      now: "Paused: its model was retired",
    },
    {
      title: "the reviewer with tasks waiting for review",
      seat: reviewer,
      tasks: [task(3, "Build the pricing table", "review", { claimant: "Theo" }), task(4, "Pick the email provider", "review", { claimant: "Priya" })],
      status: "holding",
      label: "Assigned",
      now: "To review: “Build the pricing table” and 1 other task",
    },
    {
      title: "someone else's tasks leave it idle",
      seat: maya,
      tasks: [task(3, "Build the pricing table", "claimed", { claimant: "Theo" }), task(1, "Done copy", "done", { claimant: "Maya" })],
      runs: [idleRun],
      status: "idle",
      label: "Idle",
      now: "Idle since 4 minutes ago",
    },
    {
      title: "a stood-down seat stays stood down",
      seat: seat("Maya", { state: "stood down" }),
      tasks: [task(2, "Write the FAQ", "claimed", { claimant: "Maya" })],
      status: "idle",
      label: "Idle",
      now: "Stood down",
    },
  ];
  it.each(cases)("$title", (one) => {
    const seats = one.seats ?? [one.seat, maya, priya, reviewer].filter((item, index, all) => all.findIndex((other) => other.name === item.name) === index);
    const members = crewMembers({ seats }, one.header ?? null, one.runs ?? [], one.tasks, NOW);
    const member = members.find((item) => item.name === one.seat.name);
    expect(member?.status).toBe(one.status);
    expect(member?.label).toBe(one.label);
    expect(member?.now).toBe(one.now);
    if (one.task !== undefined) expect(member?.task?.id ?? null).toBe(one.task);
    if (one.reason !== undefined) expect(member?.reason).toBe(one.reason);
    if (one.doing !== undefined) expect(member?.doing).toBe(one.doing);
  });

  it("finds who holds a blocked task: its claimant, else the team's lead, else its only member", () => {
    const seats = [seat("A", { team: "t", lead: true }), seat("B", { team: "t" }), seat("C", { team: "solo" }), seat("D", { team: "two" }), seat("E", { team: "two" })];
    expect(blockedTaskHolder(task(1, "x", "blocked", { claimant: "B", team: "t" }), seats)).toBe("B");
    expect(blockedTaskHolder(task(1, "x", "blocked", { team: "t" }), seats)).toBe("A");
    expect(blockedTaskHolder(task(1, "x", "blocked", { team: "solo" }), seats)).toBe("C");
    expect(blockedTaskHolder(task(1, "x", "blocked", { team: "two" }), seats)).toBeNull();
    expect(blockedTaskHolder(task(1, "x", "blocked"), seats)).toBeNull();
  });
});

describe("display helpers", () => {
  it.each([
    ["CEO", "CEO / Project Manager", "Project Manager"],
    ["Maya", "Marketing", "Marketing"],
    ["Reviewer", "Reviewer", "Reviewer"],
    ["Theo", "Software Engineer / Front end", "Software Engineer / Front end"],
  ])("roleLine(%s, %s) is %s", (name, role, line) => {
    expect(roleLine(name, role)).toBe(line);
  });

  it("gives each member its share of the crew's tokens", () => {
    const members = crewMembers({ seats: [seat("A"), seat("B")] }, null, [run("A", { tokens_counted: 300 }), run("B", { tokens_counted: 100 })], [], NOW);
    expect(members.map((member) => tokenShare(member, members))).toEqual([0.75, 0.25]);
    expect(tokenShare(members[0]!, [])).toBe(0);
  });
});

describe("orgTree", () => {
  it("puts the CEO on top, leads first in each team, and side seats apart", () => {
    const members = crewMembers(
      {
        seats: [
          seat("CEO", { kind: "ceo" }),
          seat("Reviewer", { kind: "reviewer" }),
          seat("writer-2", { team: "web" }),
          seat("web-lead", { team: "web", kind: "lead", lead: true }),
          seat("writer-1", { team: "web" }),
          seat("old", { team: "web", state: "stood down" }),
        ],
      },
      null,
      [],
      [],
      NOW,
    );
    const tree = orgTree(members, ["web", "empty"]);
    expect(tree.ceo?.name).toBe("CEO");
    expect(tree.teams.map((team) => team.name)).toEqual(["web"]);
    expect(tree.teams[0]?.lead?.name).toBe("web-lead");
    expect(tree.teams[0]?.members.map((member) => member.name)).toEqual(["writer-1", "writer-2"]);
    expect(tree.others.map((member) => member.name)).toEqual(["Reviewer"]);
    expect(tree.former.map((member) => member.name)).toEqual(["old"]);
    expect(statusCounts(members)).toEqual({ working: 0, holding: 0, review: 0, waiting: 0, blocked: 0, idle: 5 });
  });
});

describe("runSentence", () => {
  const cases: [string, Partial<Run>, string][] = [
    ["finished work", {}, "CEO worked on a directive, 9 minutes ago · 100 tokens"],
    ["running work", { state: "running", ended_at: null, started_at: ago(2) }, "CEO is working on a directive, started 2 minutes ago · 100 tokens"],
    ["a chat reply", { kind: "chat", reasons: ["message 4 from a person"] }, "CEO replied in chat, 9 minutes ago · 100 tokens"],
    ["a failed run", { state: "failed", reasons: ["heartbeat"] }, "CEO ran into a problem working on a regular check-in, 9 minutes ago · 100 tokens"],
    ["no tokens", { tokens_counted: 0, reasons: ["notice: project started"] }, "CEO worked on the project start, 9 minutes ago"],
    ["an unknown notice", { reasons: ["notice: something new"] }, "CEO worked on a notice about something new, 9 minutes ago · 100 tokens"],
    ["an unknown kind", { kind: "audit" }, "CEO had a run (audit, finished), 9 minutes ago · 100 tokens"],
  ];
  it.each(cases)("%s", (_title, extra, text) => {
    const sentence = runSentence(run("CEO", extra), NOW);
    expect(sentence.text).toBe(text);
    expect(sentence.text).not.toMatch(/notice:|·\s*finished/);
  });

  it("keeps the raw values for the technical fold", () => {
    const sentence = runSentence(run("CEO", { state: "failed", end_detail: "boom" }), NOW);
    expect(sentence.technical).toMatchObject({ kind: "work", state: "failed", reasons: "notice: directive issued", detail: "boom" });
    expect(sentence.tone).toBe("danger");
  });
});

describe("words", () => {
  it("joins reasons and drops repeats", () => {
    expect(reasonWords(["notice: directive issued", "notice: directive issued", "unread messages"])).toBe(
      "a directive and new messages from the crew",
    );
    expect(reasonWords([])).toBe("its own plan");
  });
  it("describes a check run", () => {
    expect(doingSentence("reading its context", "check")).toBe("Reading its context while running a check");
  });
  it("orders runs newest first", () => {
    const old = run("A", { ended_at: ago(50) });
    const fresh = run("A", { ended_at: ago(1) });
    expect(recentRuns([old, fresh, run("B")], "A")).toEqual([fresh, old]);
  });
});
