/** The project as a spec (LIB-4): download it as a JSON file, or clone it into a new project and open that. */
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api/client";
import { ErrorNote, Field } from "../components/common";
import { specFileName } from "../founder/logic";
import { t } from "../strings";

/** Hands the browser a file to save. */
function download(fileName: string, text: string): void {
  const address = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = address;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(address);
}

export function ProjectCopies({ projectId }: { projectId: string }): JSX.Element {
  const words = t.founder.copies;
  const navigate = useNavigate();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"export" | "clone" | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [cloning, setCloning] = useState(false);
  const [name, setName] = useState("");

  const run = async (what: "export" | "clone", work: () => Promise<void>): Promise<void> => {
    setBusy(what);
    setError(null);
    setSaved(null);
    try {
      await work();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(null);
    }
  };

  const exportSpec = (): Promise<void> =>
    run("export", async () => {
      const spec = await get("/v1/projects/export", { project_id: projectId });
      const fileName = specFileName(spec.name);
      download(fileName, `${JSON.stringify(spec, null, 2)}\n`);
      setSaved(fileName);
    });

  const openClone = (): Promise<void> =>
    run("clone", async () => {
      if (!name) {
        const status = await get("/v1/projects/status", { project_id: projectId });
        setName(words.cloneDefault(status.name));
      }
      setCloning(true);
    });

  const clone = (event: FormEvent): void => {
    event.preventDefault();
    void run("clone", async () => {
      const copy = await post("/v1/projects/clone", { project_id: projectId, name: name.trim() });
      navigate(`/projects/${copy.project_id}`);
    });
  };

  return (
    <section aria-labelledby="copies-title" data-testid="project-copies">
      <h3 id="copies-title">{words.title}</h3>
      <p className="quiet">{words.intro}</p>
      <div className="row wrap">
        <button type="button" className="button small" disabled={busy !== null} onClick={() => void exportSpec()}>
          {busy === "export" ? words.exporting : words.export}
        </button>
        {cloning ? null : (
          <button type="button" className="button small" disabled={busy !== null} onClick={() => void openClone()}>
            {words.clone}
          </button>
        )}
      </div>
      <p role="status" data-testid="spec-saved">
        {saved ? words.exported(saved) : ""}
      </p>
      {cloning ? (
        <form className="plan-form" onSubmit={clone} aria-label={words.cloneTitle}>
          <Field label={words.cloneName} htmlFor="clone-name">
            <input id="clone-name" required autoFocus maxLength={200} value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <div className="row wrap">
            <button type="submit" className="button primary small" disabled={busy !== null || name.trim() === ""}>
              {busy === "clone" ? words.cloning : words.cloneGo}
            </button>
            <button type="button" className="button small" onClick={() => setCloning(false)}>
              {t.common.cancel}
            </button>
          </div>
        </form>
      ) : null}
      <ErrorNote error={error} />
    </section>
  );
}
