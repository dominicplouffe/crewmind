/**
 * One project at a glance: its state, what needs you, who is working now and on what, how much of
 * the accepted scope is met, and the budget used. Every figure is the server's.
 */
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { get, type Project } from "../api/client";
import { compactNumber, share } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { useNeedsYou } from "../needs/NeedsYou";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { home, projectLayout, projectsPage } from "../strings.shell";
import { Avatar } from "../ui/Avatar";
import { Pill, type Tone } from "../ui/Status";
import { requirementProgress } from "./logic";

export const STATE_TONE: Record<string, Tone> = {
  running: "success",
  held: "warning",
  paused: "warning",
  ready: "accent",
  completed: "neutral",
  draft: "neutral",
  stopped: "neutral",
};

/** A thin bar beside its figure. The figure carries the meaning; the bar is decoration. */
function Bar({ label, value, max, text, tone }: { label: string; value: number; max: number; text: string; tone: "success" | "accent" | "danger" }): JSX.Element {
  const width = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className="pc-row">
      <span className="pc-label">{label}</span>
      <span className="pc-track" aria-hidden="true">
        <span className={`pc-fill tone-${tone}`} style={{ width: `${width}%` }} />
      </span>
      <span className="pc-value tabular">{text}</span>
    </div>
  );
}

export function ProjectCard({ project }: { project: Project }): JSX.Element {
  const needs = useNeedsYou();
  const count = needs.countFor(project.project_id);
  const live = project.state !== "deleted" && project.state !== "deleting";
  const header = useLoad(
    () => (live ? get("/v1/chat/header", { project_id: project.project_id }) : Promise.resolve(null)),
    [project.project_id, project.state],
  );
  const plan = useLoad(
    () => (live ? get("/v1/plan/show", { project_id: project.project_id }) : Promise.resolve(null)),
    [project.project_id, project.state],
  );
  const data = header.data;
  const working = data?.now ?? [];
  const first = working[0];
  const progress = requirementProgress(plan.data?.requirements);
  const atWall = data ? data.budget_spent >= data.budget_wall : false;
  return (
    <Link to={`/projects/${project.project_id}`} className="project-card" data-testid="project-card">
      <div className="project-card-head">
        <span className="project-card-name">{project.name}</span>
        <Pill tone={STATE_TONE[project.state] ?? "neutral"} live={project.state === "running" && working.length > 0}>
          {projectLayout.states[project.state] ?? project.state}
        </Pill>
      </div>
      <p className="project-card-type">
        <span>{t.projects.types[project.type as keyof typeof t.projects.types] ?? project.type}</span>
        {count > 0 ? <strong className="needs-text">{projectsPage.needs(count)}</strong> : null}
      </p>
      <div className="project-card-crew">
        {first ? (
          <>
            <span className="avatar-stack" aria-hidden="true">
              {working.slice(0, 4).map((work) => (
                <Avatar key={work.seat} name={work.seat} size="xs" status="working" />
              ))}
            </span>
            <span className="project-card-doing">
              <AgentText text={home.workingOn(first.seat, first.doing)} />
              {working.length > 1 ? <span className="quiet"> {home.andMore(working.length - 1)}</span> : null}
            </span>
          </>
        ) : (
          <span className="quiet">{data ? home.nobodyWorking : " "}</span>
        )}
      </div>
      {progress.total > 0 || (data && data.budget_wall > 0) ? (
        <div className="pc-rows">
          {progress.total > 0 ? (
            <Bar label={home.requirements} value={progress.met} max={progress.total} text={home.requirementsMet(progress.met, progress.total)} tone="success" />
          ) : null}
          {data && data.budget_wall > 0 ? (
            <Bar
              label={home.budget}
              value={data.budget_spent}
              max={data.budget_wall}
              text={home.budgetUsed(share(data.budget_spent, data.budget_wall), compactNumber(data.budget_wall))}
              tone={atWall ? "danger" : "accent"}
            />
          ) : null}
        </div>
      ) : null}
      <span className="project-card-go" aria-hidden="true">
        <ArrowRight size={16} />
      </span>
    </Link>
  );
}
