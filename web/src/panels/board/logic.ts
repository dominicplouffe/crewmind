/**
 * Display logic for the Board: the order tasks are listed in, subtasks under their parent, and the
 * sentence that says who checked a closed task. Nothing here decides anything: states and labels come
 * from the server and are only arranged.
 */
import { t } from "../../strings";

/** Open states, in the order they are listed: work in hand first. */
export const OPEN_STATES = ["claimed", "checking", "review", "ready", "blocked"] as const;
/** Closed states, folded away until asked for. */
export const CLOSED_STATES = ["done", "closed unread", "killed"] as const;

export interface TaskLike {
  id: number;
  parent_id?: number | null;
  state: string;
}

export interface TaskRow<T> {
  task: T;
  /** 0 for a task listed on its own, 1 or more for a subtask listed under its parent. */
  depth: number;
}

export interface TaskGroup<T> {
  state: string;
  rows: TaskRow<T>[];
}

export interface Grouped<T> {
  open: TaskGroup<T>[];
  closed: TaskGroup<T>[];
  closedCount: number;
}

export function isClosed(state: string): boolean {
  return (CLOSED_STATES as readonly string[]).includes(state);
}

/**
 * Groups tasks by state. A subtask is listed under its parent, in the parent's group, when the parent
 * is in the list and both are open or both closed; otherwise it is listed on its own, so an open
 * subtask is never hidden with a closed parent. A state this page does not know is listed after the
 * open ones, never dropped.
 */
export function groupTasks<T extends TaskLike>(tasks: readonly T[]): Grouped<T> {
  const byId = new Map(tasks.map((task) => [task.id, task]));
  const children = new Map<number, T[]>();
  const roots: T[] = [];
  for (const task of tasks) {
    const parent = task.parent_id == null ? undefined : byId.get(task.parent_id);
    if (parent && parent.id !== task.id && isClosed(parent.state) === isClosed(task.state)) {
      children.set(parent.id, [...(children.get(parent.id) ?? []), task]);
    } else {
      roots.push(task);
    }
  }

  const rowsUnder = (task: T, depth: number, seen: Set<number>): TaskRow<T>[] => {
    if (seen.has(task.id)) return [];
    seen.add(task.id);
    return [{ task, depth }, ...(children.get(task.id) ?? []).flatMap((child) => rowsUnder(child, depth + 1, seen))];
  };

  const seen = new Set<number>();
  const groups = new Map<string, TaskRow<T>[]>();
  for (const root of roots) {
    groups.set(root.state, [...(groups.get(root.state) ?? []), ...rowsUnder(root, 0, seen)]);
  }
  // Tasks whose parents point at each other have no root: list them on their own.
  for (const task of tasks) {
    if (!seen.has(task.id)) groups.set(task.state, [...(groups.get(task.state) ?? []), ...rowsUnder(task, 0, seen)]);
  }

  const known: readonly string[] = [...OPEN_STATES, ...CLOSED_STATES];
  const unknown = [...groups.keys()].filter((state) => !known.includes(state));
  const pick = (states: readonly string[]): TaskGroup<T>[] =>
    states.flatMap((state) => {
      const rows = groups.get(state);
      return rows ? [{ state, rows }] : [];
    });
  const closed = pick(CLOSED_STATES);
  return {
    open: pick([...OPEN_STATES, ...unknown]),
    closed,
    closedCount: closed.reduce((sum, group) => sum + group.rows.length, 0),
  };
}

/** One plain sentence saying who checked a closed task, built from its label alone. */
export function whoChecked(label: string): string {
  return t.board.whoChecked[label] ?? t.board.whoCheckedOther(label);
}

/** A class name for a label or state, so each can have its own quiet style. */
export function slug(word: string): string {
  return word.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

/** The address to link to, or null when it is not a plain web address (agent-written text is untrusted). */
export function webAddress(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}
