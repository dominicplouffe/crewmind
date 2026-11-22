/** One project as a card: name, state, what needs you, who is working, and the budget used. */
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { get, type Project } from "../api/client";
import { compactNumber, share } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { useNeedsYou } from "../needs/NeedsYou";
import { t } from "../strings";
import { projectLayout, projectsPage } from "../strings.shell";
import { Avatar } from "../ui/Avatar";
import { Meter } from "../ui/Progress";
import { Pill, type Tone } from "../ui/Status";

export const STATE_TONE: Record<string, Tone> = {
  running: "success",
  held: "warning",
  paused: "warning",
  ready: "accent",
  completed: "neutral",
  draft: "neutral",
  stopped: "neutral",
};

export function ProjectCard({ project }: { project: Project }): JSX.Element {
  const needs = useNeedsYou();
  const count = needs.countFor(project.project_id);
  const live = project.state !== "deleted" && project.state !== "deleting";
  const header = useLoad(
    () => (live ? get("/v1/chat/header", { project_id: project.project_id }) : Promise.resolve(null)),
    [project.project_id, project.state],
  );
  const data = header.data;
  const working = data?.now ?? [];
  return (
    <Link to={`/projects/${project.project_id}`} className="project-card" data-testid="project-card">
      <div className="project-card-head">
        <span className="project-card-name">{project.name}</span>
        <Pill tone={STATE_TONE[project.state] ?? "neutral"} live={project.state === "running" && working.length > 0}>
          {projectLayout.states[project.state] ?? project.state}
        </Pill>
      </div>
      <p className="quiet project-card-type">
        {t.projects.types[project.type as keyof typeof t.projects.types] ?? project.type}
        {count > 0 ? (
          <>
            {" · "}
            <strong className="needs-text">{projectsPage.needs(count)}</strong>
          </>
        ) : null}
      </p>
      <div className="project-card-crew">
        {working.length > 0 ? (
          <>
            <span className="avatar-stack" aria-hidden="true">
              {working.slice(0, 4).map((work) => (
                <Avatar key={work.seat} name={work.seat} size="sm" status="working" />
              ))}
            </span>
            <span className="quiet">{projectLayout.working(working.length)}</span>
          </>
        ) : (
          <span className="quiet">{projectLayout.working(0)}</span>
        )}
      </div>
      {data && data.budget_wall > 0 ? (
        <div className="project-card-budget">
          <Meter value={data.budget_spent} max={data.budget_wall} label={data.budget} tone={data.budget_spent >= data.budget_wall ? "danger" : "accent"} />
          <span className="quiet tabular">
            {compactNumber(data.budget_spent)} / {compactNumber(data.budget_wall)} tokens · {share(data.budget_spent, data.budget_wall)}
          </span>
        </div>
      ) : null}
      <span className="project-card-go" aria-hidden="true">
        <ArrowRight size={16} />
      </span>
    </Link>
  );
}
