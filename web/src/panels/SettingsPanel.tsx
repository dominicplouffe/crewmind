/**
 * Project settings in the side panel (GOV-1): grouped, in plain words and units, edited in place.
 * Changes are saved together with one reason, which the server keeps in the project's history.
 * Exporting and cloning the project sit at the top; personal preferences live in Settings.
 */
import { Link } from "react-router-dom";
import { get, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { SettingsForm } from "../settings/SettingsForm";
import { settingsWords } from "../strings.settings";
import { Skeleton } from "../ui/Skeleton";
import { ApprovedClients } from "./ApprovedClients";
import { ProjectCopies } from "./ProjectCopies";

export function SettingsPanel({ projectId, changes }: { projectId: string; changes: number }): JSX.Element {
  const words = settingsWords.panel;
  const project = useLoad(() => get("/v1/settings/show_project", { project_id: projectId }), [projectId, changes]);

  return (
    <>
      <ProjectCopies projectId={projectId} />
      <section className="settings-panel" aria-labelledby="project-settings-title">
        <div className="settings-panel-head">
          <h3 id="project-settings-title">{words.title}</h3>
          <p className="quiet">{words.intro}</p>
        </div>
        {project.error ? (
          <div className="stack">
            <ErrorNote error={project.error} />
            <div>
              <button type="button" className="button small" onClick={project.reload}>
                {settingsWords.common.retry}
              </button>
            </div>
          </div>
        ) : null}
        {project.loading && !project.data ? <Skeleton lines={8} /> : null}
        {project.data ? (
          <SettingsForm
            label={words.title}
            view={project.data}
            grouped
            needsReason
            onSave={async (changed, reason) => {
              project.setData(await post("/v1/settings/change_project", { project_id: projectId, changes: changed, reason }));
            }}
          />
        ) : null}
      </section>
      <div className="note settings-panel-personal">
        <p className="note-title">{words.personalTitle}</p>
        <p className="note-hint">
          {words.personalBody} <Link to="/settings/profile">{words.personalLink}</Link>
        </p>
      </div>
      <ApprovedClients />
    </>
  );
}
