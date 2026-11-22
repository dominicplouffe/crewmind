/** The Desk: everything that waits on the person, across their projects, and the daily brief below it. */
import { useCallback, useEffect } from "react";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { useAuth } from "../auth";
import { AlertsButton } from "../components/AlertsButton";
import { Empty, ErrorNote, Loading } from "../components/common";
import { ThemeButton } from "../components/ThemeButton";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { Brief } from "./Brief";
import { ItemCard } from "./ItemCard";
import { groupByProject, type DeskEntry } from "./logic";
import { Snooze } from "./Snooze";

/** The Desk spans projects and no live stream does, so it asks again this often while it is in view. */
const REFRESH_EVERY_MS = 15000;

function Entry({ entry, onChanged }: { entry: DeskEntry; onChanged(): void }): JSX.Element {
  const words = t.decisions.desk;
  if (entry.item) {
    return (
      <li data-testid="desk-entry">
        <ItemCard item={entry.item} onChanged={onChanged} />
        <Snooze item={entry.item} onDone={onChanged} />
      </li>
    );
  }
  return (
    <li data-testid="desk-entry">
      <p className="record-text">
        <AgentText text={entry.title} />
      </p>
      <p className="quiet row wrap">
        <span className="marker">{words.what[entry.what] ?? entry.what}</span>
        {entry.deadline ? <span>{words.due(formatDateTime(entry.deadline))}</span> : null}
      </p>
      <p className="quiet">{words.noItemHint}</p>
    </li>
  );
}

export function DeskPage(): JSX.Element {
  const words = t.decisions.desk;
  const { person, signOut } = useAuth();
  const desk = useLoad(() => get("/v1/desk/show"), []);
  const brief = useLoad(() => get("/v1/brief/show"), []);
  const groups = groupByProject(desk.data?.waiting ?? []);

  useEffect(() => {
    document.title = words.pageTitle;
    return () => {
      document.title = t.app.name;
    };
  }, [words.pageTitle]);

  const { reload } = desk;
  useEffect(() => {
    const again = (): void => {
      if (document.visibilityState === "visible") reload();
    };
    const timer = window.setInterval(again, REFRESH_EVERY_MS);
    document.addEventListener("visibilitychange", again);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", again);
    };
  }, [reload]);

  const { reload: reloadBrief } = brief;
  const changed = useCallback(() => {
    reload();
    reloadBrief();
  }, [reload, reloadBrief]);

  return (
    <div className="page">
      <header className="appbar">
        <Link to="/" className="brand">
          {t.app.name}
        </Link>
        <Link to="/" className="button small">
          {words.projectsLink}
        </Link>
        <span className="spacer" />
        <span className="quiet who">{person?.name}</span>
        <AlertsButton />
        <ThemeButton />
        <button type="button" className="button" onClick={() => void signOut()}>
          {t.app.signOut}
        </button>
      </header>
      <main className="page-main">
        <h1>{words.title}</h1>
        <p className="quiet">{words.intro}</p>
        <ErrorNote error={desk.error} />
        {desk.loading && !desk.data ? <Loading /> : null}
        {desk.data && groups.length === 0 ? <Empty title={words.emptyTitle} next={words.emptyNext} /> : null}
        {groups.map((group) => (
          <section key={group.projectId} className="desk-group" aria-labelledby={`desk-${group.projectId}`} data-testid="desk-project">
            <div className="row spread">
              <h2 id={`desk-${group.projectId}`}>{group.name}</h2>
              <Link to={`/projects/${group.projectId}`}>
                {words.openProject}
                <span className="visually-hidden"> {words.openProjectOf(group.name)}</span>
              </Link>
            </div>
            <ul className="records plain" aria-label={words.projectList(group.name)}>
              {group.entries.map((entry, index) => (
                <Entry key={entry.item ? `item-${entry.item.id}` : `${entry.what}-${index}`} entry={entry} onChanged={changed} />
              ))}
            </ul>
          </section>
        ))}
        <ErrorNote error={brief.error} />
        {brief.data ? <Brief brief={brief.data} /> : null}
      </main>
    </div>
  );
}
