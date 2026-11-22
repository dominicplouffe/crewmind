import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { countChanges, sideBySide } from "../lib/diff";
import { DiffTable } from "./Compare";

afterEach(cleanup);

describe("sideBySide", () => {
  it("pairs changed lines and keeps line numbers on each side", () => {
    const rows = sideBySide("one\ntwo\nthree\n", "one\n2\nthree\nfour\n");
    expect(rows.map((row) => [row.kind, row.left, row.right, row.leftNumber, row.rightNumber])).toEqual([
      ["same", "one", "one", 1, 1],
      ["changed", "two", "2", 2, 2],
      ["same", "three", "three", 3, 3],
      ["added", null, "four", null, 4],
    ]);
    expect(countChanges(rows)).toEqual({ added: 2, removed: 1 });
  });

  it("shows removed lines with a gap on the right", () => {
    const rows = sideBySide("keep\ndrop\n", "keep\n");
    expect(rows[1]).toMatchObject({ kind: "removed", left: "drop", right: null, leftNumber: 2, rightNumber: null });
  });

  it("reports identical texts as unchanged", () => {
    expect(countChanges(sideBySide("same\n", "same\n"))).toEqual({ added: 0, removed: 0 });
  });
});

describe("DiffTable", () => {
  it("renders both versions side by side with a summary and labelled changes", () => {
    render(<DiffTable rows={sideBySide("one\ntwo\n", "one\n2\nthree\n")} leftLabel="Version 1" rightLabel="Version 2" />);
    expect(screen.getByRole("status").textContent).toBe("2 lines added or changed, 1 line removed or changed.");
    expect(screen.getByRole("columnheader", { name: "Version 1" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Version 2" })).toBeTruthy();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[1]?.className).toBe("diff-changed");
    expect(within(rows[1] as HTMLElement).getByText("Changed")).toBeTruthy();
    expect(within(rows[1] as HTMLElement).getByText("two")).toBeTruthy();
    expect(within(rows[1] as HTMLElement).getByText("2", { selector: ".diff-right" })).toBeTruthy();
    expect(rows[2]?.className).toBe("diff-added");
  });

  it("says so when the versions are the same", () => {
    render(<DiffTable rows={sideBySide("a\n", "a\n")} leftLabel="Version 1" rightLabel="Version 2" />);
    expect(screen.getByRole("status").textContent).toBe("The two versions are the same.");
  });
});
