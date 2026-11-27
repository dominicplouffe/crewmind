/**
 * Home: "What needs me?" answered first, in one sentence, then the decisions themselves grouped by
 * how soon they fall due, and the projects at a glance beside them. The inbox is the desk (HUM-10):
 * the same list every badge and count reads, with one-click decisions.
 */
import { useId, useRef, useState } from "react";
import { BellRing, CheckCircle2, Newspaper, Plus, Sparkles, WifiOff } from "lucide-react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { get } from "../api/client";
import { useAuth } from "../auth";
import { Brief } from "../desk/Brief";
import { Unfinished } from "../founder/Unfinished";
import { InboxItem } from "../home/InboxItem";
import { inboxGroups, summaryLine, type InboxGroup } from "../home/logic";
import { ProjectCard } from "../home/ProjectCard";
import { useListKeys } from "../home/useListKeys";
import { firstName, greeting } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { useNeedsYou, usePageTitle } from "../needs/NeedsYou";
import { opensWelcome, welcomeSeen } from "../onboarding/firstRun";
import { useSetupStatus } from "../onboarding/useSetupStatus";
import { sortProjects, useProjects, LIVE_STATES } from "../shell/projects";
import { useAlerts } from "../shell/useAlerts";
import { home } from "../strings.shell";
import { Skeleton } from "../ui/Skeleton";

const ALERTS_DISMISSED = "nightsquad.alerts-prompt-dismissed";
const DAY_FORMAT = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" });

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(ALERTS_DISMISSED) === "1";
  } catch {
    return false;
  }
}

function AlertsPrompt({ needed }: { needed: boolean }): JSX.Element | null {
  const alerts = useAlerts();
  const [dismissed, setDismissed] = useState(readDismissed);
  if (alerts.state !== "off" || dismissed || !needed) return null;
  const dismiss = (): void => {
    setDismissed(true);
    try {
      window.localStorage.setItem(ALERTS_DISMISSED, "1");
    } catch {
      // Hidden for this visit only.
    }
  };
  return (
    <section className="callout callout-slim" aria-labelledby="alerts-title">
      <BellRing size={16} aria-hidden="true" className="callout-slim-icon" />
      <div className="callout-text">
        <h2 id="alerts-title">{home.alertsTitle}</h2>
        <p className="quiet">{home.alertsNext}</p>
      </div>
      <div className="callout-actions">
        <button type="button" className="button primary small" onClick={() => void alerts.toggle()} disabled={alerts.busy}>
          {home.alertsAction}
        </button>
        <button type="button" className="button ghost small" onClick={dismiss}>
          {home.alertsDismiss}
        </button>
      </div>
    </section>
  );
}

function SetupPrompt({ setup }: { setup: ReturnType<typeof useSetupStatus> }): JSX.Element | null {
  if (setup.loading || setup.founderReady) return null;
  return (
    <section className="callout callout-slim callout-accent" aria-labelledby="setup-title" data-testid="setup-prompt">
      <Sparkles size={16} aria-hidden="true" className="callout-slim-icon" />
      <div className="callout-text">
        <h2 id="setup-title">{home.setupTitle}</h2>
        <p className="quiet">{setup.isAdmin ? home.setupNext : home.setupMember}</p>
      </div>
      {setup.isAdmin ? (
        <div className="callout-actions">
          <Link to="/welcome" className="button primary small">
            {home.setupAction}
          </Link>
        </div>
      ) : null}
    </section>
  );
}

function Group({ group, onChanged }: { group: InboxGroup; onChanged(): void }): JSX.Element {
  const id = useId();
  const name = home.groups[group.key] ?? group.key;
  return (
    <section className={`inbox-group group-${group.key}`} aria-labelledby={id}>
      <h3 className="inbox-group-title" id={id}>
        <span>{name}</span>
        <span className="inbox-group-count" aria-hidden="true">
          {group.entries.length}
        </span>
        <span className="visually-hidden">{home.groupCount(group.entries.length)}</span>
      </h3>
      <ul className="plain inbox-list">
        {group.entries.map((entry, index) => (
          <InboxItem key={entry.item ? `item-${entry.project_id}-${entry.item.id}` : `${entry.project_id}-${entry.what}-${index}`} entry={entry} onChanged={onChanged} />
        ))}
      </ul>
    </section>
  );
}

export function Home(): JSX.Element {
  usePageTitle(home.title);
  const { person } = useAuth();
  const needs = useNeedsYou();
  const projects = useProjects();
  const navigate = useNavigate();
  const brief = useLoad(() => get("/v1/brief/show"), []);
  const setup = useSetupStatus();
  const inbox = useRef<HTMLDivElement>(null);
  useListKeys(inbox, '[data-testid="desk-entry"]');
  // The page appears in one pass once its parts have answered, so nothing jumps as they arrive.
  const ready =
    (needs.loaded || Boolean(needs.error)) &&
    !setup.loading &&
    (brief.data !== undefined || Boolean(brief.error)) &&
    (projects.data !== undefined || Boolean(projects.error));
  const list = sortProjects(projects.data?.items ?? []).filter((project) => project.state !== "deleted");
  const live = list.filter((project) => LIVE_STATES.includes(project.state) || project.state === "draft");
  const groups = inboxGroups(needs.entries);
  const changed = (): void => {
    needs.reload();
    brief.reload();
  };
  const hello = home.greeting(greeting(), firstName(person?.name));
  const firstRun =
    ready &&
    projects.data !== undefined &&
    opensWelcome({ isAdmin: setup.isAdmin, founderReady: setup.founderReady, projects: list.length, seen: welcomeSeen() });
  if (firstRun) return <Navigate to="/welcome" replace />;

  return (
    <main className="content home" aria-labelledby="home-title">
      <header className="home-head">
        <div className="home-head-text">
          <p className="home-hello">
            {hello}
            <span aria-hidden="true"> · </span>
            <span>{home.today(DAY_FORMAT.format(new Date()))}</span>
          </p>
          <h1 id="home-title" className="home-summary" aria-live="polite" data-testid="home-summary">
            {!needs.loaded ? " " : summaryLine(needs.entries, needs.byProject.size)}
          </h1>
        </div>
        <button type="button" className="button primary" onClick={() => navigate("/draft")}>
          <Plus size={16} aria-hidden="true" />
          {home.start}
        </button>
      </header>

      {!ready ? (
        <div className="home-grid" aria-busy="true">
          <Skeleton lines={3} block />
          <Skeleton lines={2} block />
        </div>
      ) : (
        <>
          <SetupPrompt setup={setup} />

          <div className="home-grid">
            <section className="home-inbox" aria-labelledby="inbox-title">
              <div className="section-head">
                <h2 id="inbox-title">
                  {home.inbox}
                  {needs.count > 0 ? (
                    <span className="count" data-testid="inbox-count">
                      {needs.count}
                    </span>
                  ) : null}
                </h2>
                {needs.count > 1 ? (
                  <p className="keys-hint" aria-hidden="true">
                    <kbd>J</kbd>
                    <kbd>K</kbd> {home.keysHint}
                  </p>
                ) : null}
              </div>
              {needs.error && needs.loaded ? (
                <p className="quiet stale" role="status">
                  <WifiOff size={14} aria-hidden="true" /> {home.inboxStale}
                </p>
              ) : null}
              {!needs.loaded && !needs.error ? <Skeleton lines={2} block /> : null}
              {needs.loaded && needs.count === 0 ? (
                <div className="empty inbox-empty">
                  <span className="empty-icon success" aria-hidden="true">
                    <CheckCircle2 size={22} />
                  </span>
                  <p className="empty-title">{home.inboxEmptyTitle}</p>
                  <p className="quiet">{home.inboxEmptyNext}</p>
                </div>
              ) : null}
              {needs.count > 0 ? (
                <div className="inbox-groups" ref={inbox} role="region" aria-label={home.inboxLabel} aria-keyshortcuts="j k">
                  <p className="visually-hidden">{home.keysLabel}</p>
                  {groups.map((group) => (
                    <Group key={group.key} group={group} onChanged={changed} />
                  ))}
                </div>
              ) : null}
            </section>

            <aside className="home-side" aria-label={home.projectsTitle}>
              <section className="home-projects" aria-labelledby="home-projects-title">
                <div className="section-head">
                  <h2 id="home-projects-title">{home.projectsTitle}</h2>
                  <Link to="/projects" className="button ghost small">
                    {home.allProjects}
                  </Link>
                </div>
                {!projects.data && projects.loading ? <Skeleton lines={3} block /> : null}
                {projects.data && list.length === 0 ? (
                  <div className="empty">
                    <span className="empty-icon" aria-hidden="true">
                      <Sparkles size={22} />
                    </span>
                    <p className="empty-title">{home.projectsEmptyTitle}</p>
                    <p className="quiet">{home.projectsEmptyNext}</p>
                    <div className="empty-action row wrap">
                      <Link to="/draft" className="button primary">
                        {home.start}
                      </Link>
                      <Link to="/projects?new=form" className="button">
                        {home.byForm}
                      </Link>
                    </div>
                  </div>
                ) : null}
                <Unfinished />
                <ul className="plain project-cards">
                  {(live.length > 0 ? live : list).slice(0, 6).map((project) => (
                    <li key={project.project_id}>
                      <ProjectCard project={project} />
                    </li>
                  ))}
                </ul>
              </section>
              {brief.data ? (
                <details className="home-brief">
                  <summary>
                    <Newspaper size={15} aria-hidden="true" />
                    {home.briefTitle}
                  </summary>
                  <Brief brief={brief.data} />
                </details>
              ) : null}
              <AlertsPrompt needed={live.length > 0} />
            </aside>
          </div>
        </>
      )}
    </main>
  );
}
