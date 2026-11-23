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

/** The board's columns, left to right, and the server states each one holds. */
export const BOARD_COLUMNS = [
  { id: "ready", states: ["ready"] },
  { id: "progress", states: ["claimed"] },
  { id: "review", states: ["review", "checking"] },
  { id: "blocked", states: ["blocked"] },
  { id: "done", states: CLOSED_STATES },
] as const;

export type ColumnId = (typeof BOARD_COLUMNS)[number]["id"] | "other";

export interface BoardColumn<T> {
  id: ColumnId;
  tasks: T[];
}

export interface BoardTaskLike extends TaskLike {
  requirement_id?: number | null;
}

/**
 * Tasks in board columns. Every known column is listed, even when empty; a state this page does not
 * know goes to an "other" column at the end, never dropped. Open work is listed oldest first (by id),
 * closed work newest first. With a requirement, only its tasks are placed.
 */
export function boardColumns<T extends BoardTaskLike>(tasks: readonly T[], requirementId: number | null = null): BoardColumn<T>[] {
  const shown = requirementId === null ? tasks : tasks.filter((task) => task.requirement_id === requirementId);
  const known = new Set<string>(BOARD_COLUMNS.flatMap((column) => [...column.states]));
  const columns: BoardColumn<T>[] = BOARD_COLUMNS.map((column) => {
    const states: readonly string[] = column.states;
    const inColumn = shown.filter((task) => states.includes(task.state));
    inColumn.sort((a, b) => (column.id === "done" ? b.id - a.id : a.id - b.id));
    return { id: column.id, tasks: inColumn };
  });
  const other = shown.filter((task) => !known.has(task.state)).sort((a, b) => a.id - b.id);
  if (other.length > 0) columns.push({ id: "other", tasks: other });
  return columns;
}

export interface RequirementProgress {
  /** Tasks under the requirement that are closed as done (killed tasks are not counted at all). */
  done: number;
  total: number;
  /** Who holds its open work, in the order first seen. */
  owners: string[];
}

/** How far the tasks under one requirement have got, and who holds them. */
export function requirementProgress(tasks: readonly (BoardTaskLike & { claimant: string | null })[], requirementId: number): RequirementProgress {
  const mine = tasks.filter((task) => task.requirement_id === requirementId && task.state !== "killed");
  const owners: string[] = [];
  for (const task of mine) {
    if (task.claimant && !isClosed(task.state) && !owners.includes(task.claimant)) owners.push(task.claimant);
  }
  return { done: mine.filter((task) => isClosed(task.state)).length, total: mine.length, owners };
}

/**
 * Whether a card shows its check label: once there is something to say beyond "not yet checked", or
 * when the task closed without a check. On open work "not yet checked" goes without saying.
 */
export function showsCheckLabel(task: { state: string; label: string }): boolean {
  return task.label !== "not yet checked" || isClosed(task.state);
}
