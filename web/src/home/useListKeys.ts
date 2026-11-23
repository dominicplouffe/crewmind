/**
 * J and K (and the arrow keys from a card itself) move between the entries of a list, the way mail
 * apps do. Typing in a field, or using arrows inside a choice, is left alone. A list inside a sheet
 * answers only while focus is in that sheet.
 */
import { useEffect, type RefObject } from "react";

const NEXT = new Set(["j", "ArrowDown"]);
const PREVIOUS = new Set(["k", "ArrowUp"]);

export function useListKeys(list: RefObject<HTMLElement>, selector: string): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      const root = list.current;
      if (!root || event.metaKey || event.ctrlKey || event.altKey || event.defaultPrevented) return;
      const forward = NEXT.has(event.key);
      if (!forward && !PREVIOUS.has(event.key)) return;
      const target = event.target as HTMLElement | null;
      if (!target || target.closest("input, textarea, select, [contenteditable='true'], [role='menu'], [role='listbox']")) return;
      // Inside a sheet, only the sheet's own list moves; a list on the page ignores keys in a sheet.
      const dialog = target.closest("dialog");
      if (dialog ? !dialog.contains(root) : root.closest("dialog") !== null) return;
      const entries = [...root.querySelectorAll<HTMLElement>(selector)];
      if (entries.length === 0) return;
      const current = entries.findIndex((entry) => entry.contains(target));
      // Arrows move only from an entry itself, so they still scroll the page and work in menus.
      if (event.key.startsWith("Arrow") && (current < 0 || entries[current] !== target)) return;
      const next = current < 0 ? 0 : Math.min(entries.length - 1, Math.max(0, current + (forward ? 1 : -1)));
      const element = entries[next];
      if (!element) return;
      event.preventDefault();
      element.focus();
      element.scrollIntoView({ block: "nearest" });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [list, selector]);
}
