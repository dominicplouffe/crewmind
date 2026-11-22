/** The project list: every project as a card, unfinished drafts, and starting one (the Founder, or a form). */
import { useState, type FormEvent } from "react";
import { FolderKanban, Plus } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { post, type Schemas } from "../api/client";
import { ErrorNote, Field } from "../components/common";
import { Unfinished } from "../founder/Unfinished";
import { ProjectCard } from "../home/ProjectCard";
import { usePageTitle } from "../needs/NeedsYou";
import { LIVE_STATES, sortProjects, useProjects } from "../shell/projects";
import { t } from "../strings";
import { home, projectsPage } from "../strings.shell";
import { Skeleton } from "../ui/Skeleton";

type ProjectType = Schemas["ProjectType"];
const TYPES: ProjectType[] = ["explore", "deliver", "operate"];

function NewProject({ onClose, onCreated }: { onClose(): void; onCreated(): void }): JSX.Element {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [type, setType] = useState<ProjectType>("explore");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const project = await post("/v1/projects/create", { name, type, goal });
      onCreated();
      navigate(`/projects/${project.project_id}`);
    } catch (reason) {
      setError(reason);
      setBusy(false);
    }
  };

  return (
    <form className="card" onSubmit={(event) => void submit(event)} aria-labelledby="new-project-title">
      <h2 id="new-project-title">{t.projects.newTitle}</h2>
      <Field label={t.projects.name} htmlFor="project-name">
        <input id="project-name" required autoFocus value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field label={t.projects.type} htmlFor="project-type" hint={t.projects.typeHint[type]}>
        <select
          id="project-type"
          value={type}
          aria-describedby="project-type-hint"
          onChange={(event) => setType(event.target.value as ProjectType)}
        >
          {TYPES.map((value) => (
            <option key={value} value={value}>
              {t.projects.types[value]}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t.projects.goal} htmlFor="project-goal" hint={t.projects.goalHint}>
        <textarea
          id="project-goal"
          required
          rows={4}
          aria-describedby="project-goal-hint"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
        />
      </Field>
      <ErrorNote error={error} />
      <div className="row">
        <button type="submit" className="button primary" disabled={busy}>
          {busy ? t.projects.creating : t.projects.create}
        </button>
        <button type="button" className="button" onClick={onClose}>
          {t.common.cancel}
        </button>
      </div>
    </form>
  );
}

export function Projects(): JSX.Element {
  usePageTitle(projectsPage.title);
  const projects = useProjects();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(params.get("new") === "form");
  const items = sortProjects(projects.data?.items ?? []).filter((project) => project.state !== "deleted");
  const live = items.filter((project) => LIVE_STATES.includes(project.state));
  const other = items.filter((project) => !LIVE_STATES.includes(project.state));
  const close = (): void => {
    setCreating(false);
    if (params.has("new")) setParams({}, { replace: true });
  };

  return (
    <main className="content" aria-labelledby="projects-title">
      <header className="page-head">
        <div>
          <h1 id="projects-title">{t.projects.title}</h1>
          <p>{projectsPage.intro}</p>
        </div>
        {creating ? null : (
          <div className="row wrap">
            <button type="button" className="button" onClick={() => setCreating(true)}>
              {t.founder.way.byForm}
            </button>
            <Link to="/draft" className="button primary">
              <Plus size={16} aria-hidden="true" />
              {t.founder.way.start}
            </Link>
          </div>
        )}
      </header>
      {creating ? <NewProject onClose={close} onCreated={projects.reload} /> : null}
      <ErrorNote error={projects.error} />
      {projects.loading && !projects.data ? <Skeleton lines={3} block /> : null}
      {projects.data && items.length === 0 && !creating ? (
        <div className="empty">
          <span className="empty-icon" aria-hidden="true">
            <FolderKanban size={22} />
          </span>
          <p className="empty-title">{t.projects.emptyTitle}</p>
          <p className="quiet">{t.founder.way.emptyNext}</p>
          <div className="empty-action">
            <Link to="/draft" className="button primary">
              {home.start}
            </Link>
          </div>
        </div>
      ) : null}
      {creating ? null : <Unfinished />}
      {live.length > 0 ? (
        <section aria-labelledby="projects-live">
          <h2 id="projects-live" className="eyebrow section-label">
            {projectsPage.live}
          </h2>
          <ul className="plain project-cards grid">
            {live.map((project) => (
              <li key={project.project_id}>
                <ProjectCard project={project} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {other.length > 0 ? (
        <section aria-labelledby="projects-other">
          <h2 id="projects-other" className="eyebrow section-label">
            {projectsPage.other}
          </h2>
          <ul className="plain project-cards grid">
            {other.map((project) => (
              <li key={project.project_id}>
                <ProjectCard project={project} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
