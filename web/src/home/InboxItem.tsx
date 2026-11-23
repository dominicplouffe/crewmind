/**
 * One thing that waits on the person, on Home and in a project's list. A decision item is the
 * compact decision card, with its project named; anything else (an expired bet, a frozen thread, an
 * action card) is one line that links to where it is answered.
 */
import { ArrowRight, Hourglass } from "lucide-react";
import { Link } from "react-router-dom";
import { ItemCard } from "../desk/ItemCard";
import { fromNow } from "../lib/humanize";
import { urgencyOf, type DeskEntry } from "../needs/summary";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { home } from "../strings.shell";

export function InboxItem({ entry, onChanged, showProject = true }: { entry: DeskEntry; onChanged(): void; showProject?: boolean }): JSX.Element {
  const urgency = urgencyOf(entry);
  const project = showProject ? { id: entry.project_id, name: entry.project_name } : undefined;
  return (
    <li className={`inbox-item urgency-${urgency}`} data-testid="desk-entry" tabIndex={-1}>
      {entry.item ? (
        <ItemCard item={entry.item} onChanged={onChanged} project={project} />
      ) : (
        <div className="inbox-plain">
          <Hourglass size={15} aria-hidden="true" className="inbox-plain-icon" />
          <div className="inbox-plain-text">
            <p className="inbox-title">
              <AgentText text={entry.title} />
            </p>
            <p className="dcard-meta">
              {showProject ? (
                <Link to={`/projects/${entry.project_id}`} className="dcard-project">
                  {entry.project_name}
                </Link>
              ) : null}
              <span>{home.what[entry.what] ?? t.decisions.desk.what[entry.what] ?? entry.what}</span>
              {entry.deadline ? <span className={`dcard-due urgency-${urgency}`}>{fromNow(entry.deadline)}</span> : null}
            </p>
          </div>
          <Link to={`/projects/${entry.project_id}`} className="button small">
            {home.openProject}
            <span className="visually-hidden"> {entry.project_name}</span>
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
        </div>
      )}
    </li>
  );
}
