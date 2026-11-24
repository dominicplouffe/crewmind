/**
 * Who is doing what, in sentences (CHAT-18, EXE-4, WRK-4): agents at work from the header, then
 * blocked tasks with their reason, tasks waiting for review or a check, and tasks claimed but not
 * running. Shared by the Overview and the chat's side rail. Display only: every state comes from
 * the server; nothing here decides anything.
 */
import type { Header, Task } from "../api/client";
import { doingSentence } from "../squad/logic";
import { story, type Part } from "../strings.overview";

export type NowStatus = "working" | "blocked" | "review" | "checking" | "claimed";

export interface NowEntry {
  key: string;
  /** The seat to show as an avatar, when one is known. */
  seat: string | null;
  status: NowStatus;
  parts: Part[];
  /** A second, quieter line: what the run is doing, the block's reason, or who sent the work. */
  note: string | null;
  /** True when `note` is agent text (a block's reason), shown as plain text (P4). */
  noteIsAgentText: boolean;
}

const ORDER: Record<NowStatus, number> = { working: 0, blocked: 1, review: 2, checking: 3, claimed: 4 };

type Working = Pick<Header["now"][number], "seat" | "run_kind" | "doing">;
type TaskLike = Pick<Task, "id" | "title" | "state" | "claimant" | "reason" | "team">;

/** `nameOf` gives the name an agent goes by (EXE-18); the entry's `seat` stays the identity. */
export function nowEntries(
  working: readonly Working[],
  tasks: readonly TaskLike[],
  nameOf: (seat: string) => string = (seat) => seat,
): NowEntry[] {
  const entries: NowEntry[] = [];
  const busy = new Set<string>();
  const claimedBy = new Map<string, TaskLike>();
  for (const task of tasks) {
    if (task.state === "claimed" && task.claimant && !claimedBy.has(task.claimant)) claimedBy.set(task.claimant, task);
  }

  for (const run of working) {
    if (busy.has(run.seat)) continue;
    busy.add(run.seat);
    const task = run.run_kind === "work" ? claimedBy.get(run.seat) : undefined;
    entries.push({
      key: `run-${run.seat}`,
      seat: run.seat,
      status: "working",
      parts: story.now.working(nameOf(run.seat), task?.title ?? null),
      note: doingSentence(run.doing, run.run_kind),
      noteIsAgentText: false,
    });
  }

  for (const task of tasks) {
    const key = `task-${task.id}`;
    if (task.state === "blocked") {
      entries.push({
        key,
        seat: task.claimant,
        status: "blocked",
        parts: story.now.blocked(task.title),
        note: task.reason?.trim() || story.now.noReason,
        noteIsAgentText: Boolean(task.reason?.trim()),
      });
    } else if (task.state === "review" || task.state === "checking") {
      entries.push({
        key,
        seat: task.claimant,
        status: task.state,
        parts: task.state === "review" ? story.now.review(task.title) : story.now.checking(task.title),
        note: task.claimant ? story.now.from(nameOf(task.claimant)) : task.team ? story.now.team(task.team) : null,
        noteIsAgentText: false,
      });
    } else if (task.state === "claimed" && task.claimant && !busy.has(task.claimant)) {
      entries.push({
        key,
        seat: task.claimant,
        status: "claimed",
        parts: story.now.claimed(nameOf(task.claimant), task.title),
        note: story.now.claimedNote,
        noteIsAgentText: false,
      });
    }
  }
  // A stable sort keeps the server's order inside each group.
  return entries.sort((a, b) => ORDER[a.status] - ORDER[b.status]);
}

/** The whole sentence as plain text, for labels and tests. */
export function plainText(parts: readonly Part[]): string {
  return parts.map((part) => (typeof part === "string" ? part : "who" in part ? part.who : part.title)).join("");
}
