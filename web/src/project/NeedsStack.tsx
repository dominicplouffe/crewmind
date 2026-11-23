/**
 * What waits on the person in this project, as a slim stack above the chat (HUM-10): at most the two
 * most urgent decisions, each as its ask, when it is due and its first action, and "+N more" opening
 * the full list. The entries are the one desk list every count reads.
 */
import { ArrowRight, Hourglass, Inbox } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { ItemCard } from "../desk/ItemCard";
import { fromNow } from "../lib/humanize";
import { byPriority, urgencyOf, type DeskEntry } from "../needs/summary";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { home } from "../strings.shell";

/** How many entries the stack shows before "+N more". */
const SHOWN = 2;

interface Props {
  projectId: string;
  entries: DeskEntry[];
  onChanged(): void;
  onOpenAll(): void;
}

function PlainRow({ entry, onOpenAll }: { entry: DeskEntry; onOpenAll(): void }): JSX.Element {
  const urgency = urgencyOf(entry);
  return (
    <div className="dcard is-slim" data-testid="needs-stack-item">
      <p className="dcard-slim-text">
        <Hourglass size={14} aria-hidden="true" className="dcard-slim-icon" />
        <span className="dcard-ask">
          <AgentText text={entry.title} />
        </span>
        <span className="dcard-slim-subject">{home.what[entry.what] ?? t.decisions.desk.what[entry.what] ?? entry.what}</span>
      </p>
      {entry.deadline ? <span className={`dcard-due urgency-${urgency}`}>{fromNow(entry.deadline)}</span> : null}
      <button type="button" className="button small" onClick={onOpenAll}>
        {home.openProject}
        <span className="visually-hidden"> {entry.title}</span>
      </button>
    </div>
  );
}

export function NeedsStack({ projectId, entries, onChanged, onOpenAll }: Props): JSX.Element | null {
  const id = useId();
  const narrow = useNarrow();
  if (entries.length === 0) return null;
  const sorted = [...entries].sort(byPriority);
  const shown = sorted.slice(0, narrow ? 1 : SHOWN);
  const rest = sorted.length - shown.length;
  const words = home.stack;
  return (
    <section className="needs-stack" aria-labelledby={id} data-testid="needs-stack" data-project-id={projectId}>
      <header className="needs-stack-head">
        <h2 id={id} className="needs-stack-title">
          <Inbox size={14} aria-hidden="true" />
          {words.title}
          <span className="count">{sorted.length}</span>
        </h2>
        <button type="button" className="button small ghost" onClick={onOpenAll} aria-label={words.allLabel(sorted.length)}>
          {rest > 0 ? words.more(rest) : words.all}
          <ArrowRight size={14} aria-hidden="true" />
        </button>
      </header>
      <ul className="plain needs-stack-list">
        {shown.map((entry, index) => (
          <li key={entry.item ? `item-${entry.item.id}` : `${entry.what}-${index}`}>
            {entry.item ? (
              <ItemCard item={entry.item} onChanged={onChanged} slim onOpen={onOpenAll} />
            ) : (
              <PlainRow entry={entry} onOpenAll={onOpenAll} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** On a phone the stack shows only the most urgent decision, so the conversation keeps the room. */
const NARROW = "(max-width: 599px)";

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia?.(NARROW).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.(NARROW);
    if (!media) return;
    const follow = (): void => setNarrow(media.matches);
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);
  return narrow;
}
