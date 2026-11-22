/**
 * A time shown as "4 minutes ago", with the exact time on hover and for screen readers. One shared
 * timer moves every relative time on the page forward once a minute.
 */
import { useEffect, useState } from "react";
import { formatDateTime } from "../lib/format";
import { fromNow } from "../lib/humanize";

const TICK_MS = 60_000;
const listeners = new Set<() => void>();
let timer: number | undefined;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === undefined) timer = window.setInterval(() => listeners.forEach((call) => call()), TICK_MS);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== undefined) {
      window.clearInterval(timer);
      timer = undefined;
    }
  };
}

/** The current time, updated once a minute. */
export function useMinute(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => subscribe(() => setNow(Date.now())), []);
  return now;
}

export function RelativeTime({ at, className }: { at: string; className?: string }): JSX.Element {
  const now = useMinute();
  const exact = formatDateTime(at);
  return (
    <time dateTime={at} title={exact} className={className}>
      <span aria-hidden="true">{fromNow(at, now)}</span>
      <span className="visually-hidden">{exact}</span>
    </time>
  );
}
