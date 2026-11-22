/**
 * Home: "What needs me?" first, then the projects at a glance. The inbox is the desk (HUM-10):
 * the same list every badge and count reads, soonest deadline first, with one-click decisions.
 */
import { useState } from "react";
import { BellRing, CheckCircle2, Plus, Sparkles, WifiOff } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { get } from "../api/client";
import { useAuth } from "../auth";
import { Brief } from "../desk/Brief";
import { Unfinished } from "../founder/Unfinished";
import { InboxItem } from "../home/InboxItem";
import { ProjectCard } from "../home/ProjectCard";
import { firstName, greeting } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { useNeedsYou, usePageTitle } from "../needs/NeedsYou";
import { useSetupStatus } from "../onboarding/useSetupStatus";
import { sortProjects, useProjects, LIVE_STATES } from "../shell/projects";
import { useAlerts } from "../shell/useAlerts";
import { home } from "../strings.shell";
import { Skeleton } from "../ui/Skeleton";

const ALERTS_DISMISSED = "crewmind.alerts-prompt-dismissed";

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
    <section className="callout" aria-labelledby="alerts-title">
      <span className="callout-icon" aria-hidden="true">
        <BellRing size={18} />
      </span>
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

function SetupPrompt(): JSX.Element | null {
  const setup = useSetupStatus();
  if (setup.loading || setup.founderReady) return null;
  return (
    <section className="callout callout-accent" aria-labelledby="setup-title" data-testid="setup-prompt">
      <span className="callout-icon" aria-hidden="true">
        <Sparkles size={18} />
      </span>
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

export function Home(): JSX.Element {
  usePageTitle(home.title);
  const { person } = useAuth();
  const needs = useNeedsYou();
  const projects = useProjects();
  const navigate = useNavigate();
  const brief = useLoad(() => get("/v1/brief/show"), []);
  const list = sortProjects(projects.data?.items ?? []).filter((project) => project.state !== "deleted");
  const live = list.filter((project) => LIVE_STATES.includes(project.state) || project.state === "draft");
  const projectCount = needs.byProject.size;
  const changed = (): void => {
    needs.reload();
    brief.reload();
  };

  return (
    <main className="content home" aria-labelledby="home-title">
      <header className="home-head">
        <div>
          <h1 id="home-title">{home.greeting(greeting(), firstName(person?.name))}</h1>
          <p className="home-summary" role="status" data-testid="home-summary">
            {!needs.loaded ? " " : needs.count === 0 ? home.summaryNone : home.summary(needs.count, projectCount)}
          </p>
        </div>
        <button type="button" className="button primary" onClick={() => navigate("/draft")}>
          <Plus size={16} aria-hidden="true" />
          {home.start}
        </button>
      </header>

      <SetupPrompt />

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
            <ul className="plain inbox-list" aria-label={home.inboxLabel}>
              {needs.entries.map((entry, index) => (
                <InboxItem key={entry.item ? `item-${entry.project_id}-${entry.item.id}` : `${entry.project_id}-${entry.what}-${index}`} entry={entry} onChanged={changed} />
              ))}
            </ul>
          ) : null}
          <AlertsPrompt needed={live.length > 0} />
          {brief.data ? (
            <details className="home-brief">
              <summary>{home.briefTitle}</summary>
              <Brief brief={brief.data} />
            </details>
          ) : null}
        </section>

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
      </div>
    </main>
  );
}
