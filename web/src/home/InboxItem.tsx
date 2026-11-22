/**
 * One thing that waits on the person, on Home. Decision items show the full decision card with
 * one-click actions; the rest (expired bets, frozen threads, action cards) link to where they are
 * answered. The project it belongs to is always named.
 */
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { ItemCard } from "../desk/ItemCard";
import { Snooze } from "../desk/Snooze";
import { fromNow } from "../lib/humanize";
import { urgencyOf, type DeskEntry } from "../needs/summary";
import { t } from "../strings";
import { home } from "../strings.shell";

export function InboxItem({ entry, onChanged, showProject = true }: { entry: DeskEntry; onChanged(): void; showProject?: boolean }): JSX.Element {
  const urgency = urgencyOf(entry);
  return (
    <li className={`inbox-item urgency-${urgency}`} data-testid="desk-entry">
      {showProject ? (
        <div className="inbox-project">
          <Link to={`/projects/${entry.project_id}`} className="inbox-project-link">
            {entry.project_name}
          </Link>
        </div>
      ) : null}
      {entry.item ? (
        <>
          <ItemCard item={entry.item} onChanged={onChanged} />
          <div className="inbox-foot">
            <Snooze item={entry.item} onDone={onChanged} />
          </div>
        </>
      ) : (
        <div className="inbox-plain">
          <div>
            <p className="inbox-title">{entry.title}</p>
            <p className="quiet">
              {home.what[entry.what] ?? t.decisions.desk.what[entry.what] ?? entry.what}
              {entry.deadline ? ` · ${fromNow(entry.deadline)}` : ""}
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
