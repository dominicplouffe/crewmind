/** Builds the rows of a side-by-side comparison of two texts. */
import { diffLines } from "diff";

export type RowKind = "same" | "changed" | "added" | "removed";

export interface DiffRow {
  kind: RowKind;
  left: string | null;
  right: string | null;
  leftNumber: number | null;
  rightNumber: number | null;
}

function lines(value: string): string[] {
  const parts = value.split("\n");
  if (parts[parts.length - 1] === "") parts.pop();
  return parts;
}

/** Pairs removed lines with the added lines that replace them, so changes sit side by side. */
export function sideBySide(before: string, after: string): DiffRow[] {
  const rows: DiffRow[] = [];
  let leftNumber = 0;
  let rightNumber = 0;
  const parts = diffLines(before, after);
  for (let i = 0; i < parts.length; i += 1) {
    const part = parts[i];
    if (!part) continue;
    const next = parts[i + 1];
    if (part.removed && next?.added) {
      const removed = lines(part.value);
      const added = lines(next.value);
      for (let j = 0; j < Math.max(removed.length, added.length); j += 1) {
        const left = removed[j] ?? null;
        const right = added[j] ?? null;
        rows.push({
          kind: left !== null && right !== null ? "changed" : left !== null ? "removed" : "added",
          left,
          right,
          leftNumber: left !== null ? (leftNumber += 1) : null,
          rightNumber: right !== null ? (rightNumber += 1) : null,
        });
      }
      i += 1;
    } else if (part.removed) {
      for (const left of lines(part.value)) {
        rows.push({ kind: "removed", left, right: null, leftNumber: (leftNumber += 1), rightNumber: null });
      }
    } else if (part.added) {
      for (const right of lines(part.value)) {
        rows.push({ kind: "added", left: null, right, leftNumber: null, rightNumber: (rightNumber += 1) });
      }
    } else {
      for (const line of lines(part.value)) {
        rows.push({
          kind: "same",
          left: line,
          right: line,
          leftNumber: (leftNumber += 1),
          rightNumber: (rightNumber += 1),
        });
      }
    }
  }
  return rows;
}

export function countChanges(rows: DiffRow[]): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const row of rows) {
    if (row.kind === "added" || row.kind === "changed") added += 1;
    if (row.kind === "removed" || row.kind === "changed") removed += 1;
  }
  return { added, removed };
}
