import { describe, expect, it } from "vitest";
import { groupTasks, isClosed, slug, webAddress, whoChecked, type TaskLike } from "./logic";

const task = (id: number, state: string, parent_id: number | null = null): TaskLike => ({ id, state, parent_id });
const shape = (groups: { state: string; rows: { task: TaskLike; depth: number }[] }[]): [string, [number, number][]][] =>
  groups.map((group) => [group.state, group.rows.map((row) => [row.task.id, row.depth])]);

describe("groupTasks", () => {
  it("lists open states in the order claimed, checking, review, ready, blocked", () => {
    const grouped = groupTasks([
      task(1, "blocked"),
      task(2, "ready"),
      task(3, "review"),
      task(4, "checking"),
      task(5, "claimed"),
      task(6, "ready"),
    ]);
    expect(shape(grouped.open)).toEqual([
      ["claimed", [[5, 0]]],
      ["checking", [[4, 0]]],
      ["review", [[3, 0]]],
      ["ready", [[2, 0], [6, 0]]],
      ["blocked", [[1, 0]]],
    ]);
    expect(grouped.closed).toEqual([]);
    expect(grouped.closedCount).toBe(0);
  });

  it("keeps closed tasks apart, in the order done, closed unread, killed", () => {
    const grouped = groupTasks([task(1, "killed"), task(2, "closed unread"), task(3, "done"), task(4, "ready")]);
    expect(shape(grouped.open)).toEqual([["ready", [[4, 0]]]]);
    expect(shape(grouped.closed)).toEqual([
      ["done", [[3, 0]]],
      ["closed unread", [[2, 0]]],
      ["killed", [[1, 0]]],
    ]);
    expect(grouped.closedCount).toBe(3);
  });

  it("lists subtasks under their parent, in the parent's group, whatever their own open state", () => {
    const grouped = groupTasks([task(1, "claimed"), task(2, "ready"), task(3, "ready", 1), task(4, "review", 1)]);
    expect(shape(grouped.open)).toEqual([
      ["claimed", [[1, 0], [3, 1], [4, 1]]],
      ["ready", [[2, 0]]],
    ]);
  });

  it("never hides an open subtask with its closed parent, or the other way round", () => {
    const grouped = groupTasks([task(1, "done"), task(2, "ready", 1), task(3, "done", 1), task(4, "claimed"), task(5, "killed", 4)]);
    expect(shape(grouped.open)).toEqual([
      ["claimed", [[4, 0]]],
      ["ready", [[2, 0]]],
    ]);
    expect(shape(grouped.closed)).toEqual([
      ["done", [[1, 0], [3, 1]]],
      ["killed", [[5, 0]]],
    ]);
  });

  it("lists a subtask on its own when its parent is not in the list", () => {
    expect(shape(groupTasks([task(7, "ready", 99)]).open)).toEqual([["ready", [[7, 0]]]]);
  });

  it("lists a state it does not know after the open ones, and drops nothing", () => {
    const grouped = groupTasks([task(1, "paused"), task(2, "ready"), task(3, "claimed", 4), task(4, "claimed", 3)]);
    expect(grouped.open.map((group) => group.state)).toEqual(["claimed", "ready", "paused"]);
    const ids = grouped.open.flatMap((group) => group.rows.map((row) => row.task.id)).sort();
    expect(ids).toEqual([1, 2, 3, 4]);
  });
});

describe("isClosed", () => {
  it.each([
    ["done", true],
    ["closed unread", true],
    ["killed", true],
    ["ready", false],
    ["claimed", false],
    ["checking", false],
    ["review", false],
    ["blocked", false],
  ])("%s → %s", (state, closed) => {
    expect(isClosed(state)).toBe(closed);
  });
});

describe("whoChecked", () => {
  it.each([
    ["verified", "The platform ran the test and it passed."],
    ["reviewed", "An independent reviewer read it and passed it."],
    ["self-reported", "Nobody checked this: it is self-reported."],
    ["closed unread", "No reviewer was left, so it closed unread."],
    ["not yet checked", "It closed before anything checked it."],
  ])("%s", (label, sentence) => {
    expect(whoChecked(label)).toBe(sentence);
  });

  it("says the platform checked only for the label verified", () => {
    for (const label of ["reviewed", "self-reported", "closed unread", "not yet checked", "something new"]) {
      expect(whoChecked(label)).not.toMatch(/platform ran|verified/i);
    }
  });

  it("shows a label it does not know as given", () => {
    expect(whoChecked("checked twice")).toBe("The server labels this “checked twice”.");
  });
});

describe("slug", () => {
  it("makes a class name from a label", () => {
    expect(slug("closed unread")).toBe("closed-unread");
    expect(slug("self-reported")).toBe("self-reported");
  });
});

describe("webAddress", () => {
  it("links only to plain web addresses", () => {
    expect(webAddress("https://example.com/a?b=1")).toBe("https://example.com/a?b=1");
    expect(webAddress("http://example.com")).toBe("http://example.com/");
    expect(webAddress("javascript:alert(1)")).toBeNull();
    expect(webAddress("data:text/html,hi")).toBeNull();
    expect(webAddress("not an address")).toBeNull();
  });
});
