/**
 * What the Founder is doing right now and for how long, counted up every second, so a long step
 * is never a still page (P17). With nothing reported yet it says only that the Founder is working.
 */
import { useEffect, useState } from "react";
import { founder as words } from "../strings.founder";
import { elapsedWords, secondsSince } from "./conversation";

interface Props {
  doing: string;
  since: string;
}

export function WorkingLine({ doing, since }: Props): JSX.Element {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = secondsSince(since, now);
  return (
    <p className="quiet" role="status" data-testid="waiting-for-founder">
      {doing
        ? words.talk.founderIsWorking(doing, seconds === null ? "" : elapsedWords(seconds))
        : words.talk.waitingForFounder}
    </p>
  );
}
