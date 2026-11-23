/**
 * Two-key shortcuts ("g" then a letter), as in Linear and GitHub. Ignored while the person is
 * typing in a field, and when a modifier key is held, so they never steal text input.
 */
import { useEffect, useRef } from "react";

/** How long after "g" the second key still counts. A display convenience, not a rule. */
const SEQUENCE_MS = 1200;

export function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function useGoShortcuts(map: Record<string, () => void>): void {
  const armed = useRef(0);
  const latest = useRef(map);
  latest.current = map;
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (document.querySelector("dialog[open]")) return;
      const key = event.key.toLowerCase();
      if (key === "g") {
        armed.current = Date.now();
        return;
      }
      if (Date.now() - armed.current > SEQUENCE_MS) return;
      const run = latest.current[key];
      if (run) {
        event.preventDefault();
        armed.current = 0;
        run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
