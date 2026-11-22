/** The project list: starting a project by talking with the Founder, unfinished drafts, and the form as the other way. */
import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { get, post, type Schemas } from "../api/client";
import { useAuth } from "../auth";
import { AlertsButton } from "../components/AlertsButton";
import { Empty, ErrorNote, Field, Loading } from "../components/common";
import { ThemeButton } from "../components/ThemeButton";
import { DeskLink } from "../desk/DeskLink";
import { Unfinished } from "../founder/Unfinished";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";

type ProjectType = Schemas["ProjectType"];
const TYPES: ProjectType[] = ["explore", "deliver", "operate"];

function NewProject({ onClose }: { onClose(): void }): JSX.Element {
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
  const { person, signOut } = useAuth();
  const projects = useLoad(() => get("/v1/projects/list", {}), []);
  const [creating, setCreating] = useState(false);
  const newButton = useRef<HTMLButtonElement>(null);
  const items = projects.data?.items ?? [];

  return (
    <div className="page">
      <header className="appbar">
        <span className="brand">{t.app.name}</span>
        <DeskLink />
        <span className="spacer" />
        <span className="quiet who">{person?.name}</span>
        <AlertsButton />
        <ThemeButton />
        <button type="button" className="button" onClick={() => void signOut()}>
          {t.app.signOut}
        </button>
      </header>
      <main className="page-main">
        <div className="row spread wrap">
          <h1>{t.projects.title}</h1>
          {creating ? null : (
            <div className="row wrap">
              <Link to="/draft" className="button primary">
                {t.founder.way.start}
              </Link>
              <button type="button" className="button" ref={newButton} onClick={() => setCreating(true)}>
                {t.founder.way.byForm}
              </button>
            </div>
          )}
        </div>
        {creating ? <NewProject onClose={() => setCreating(false)} /> : null}
        <ErrorNote error={projects.error} />
        {projects.loading && !projects.data ? <Loading /> : null}
        {projects.data && items.length === 0 && !creating ? (
          <Empty title={t.projects.emptyTitle} next={t.founder.way.emptyNext} />
        ) : null}
        {creating ? null : <Unfinished />}
        <ul className="project-list">
          {items.map((project) => (
            <li key={project.project_id}>
              <Link to={`/projects/${project.project_id}`} className="project-link">
                <span className="project-name">{project.name}</span>
                <span className="quiet">
                  {t.projects.line(t.projects.types[project.type as ProjectType] ?? project.type, project.state)}
                </span>
                <span className="quiet">{t.projects.created(formatDateTime(project.created_at))}</span>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
