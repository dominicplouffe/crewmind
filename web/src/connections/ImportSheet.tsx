/**
 * Pasting a `.env` (CON-2): the text goes to the server for a review of names, kinds and
 * problems (never values), each line can be switched between secret and variable or skipped,
 * and saving adds all of them or none. The text is cleared once saved.
 */
import { useId, useState } from "react";
import { post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { connectionWords as words } from "../strings.connections";
import { Sheet } from "../ui/Sheet";
import { RolePicker } from "./RolePicker";

type Line = Schemas["ImportLine"];

interface Props {
  scope: "person" | "install" | "project";
  projectId?: string;
  /** In a project: the roles to choose from, for lines no role declared a need for. */
  roleOptions?: Schemas["RoleOption"][];
  onClose(): void;
  onSaved(count: number): void;
}

export function ImportSheet({ scope, projectId, roleOptions, onClose, onSaved }: Props): JSX.Element {
  const id = useId();
  const [text, setText] = useState("");
  const [lines, setLines] = useState<Line[] | null>(null);
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [skip, setSkip] = useState<string[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const body = (skipped: string[], chosen: Record<string, string>) => ({
    text,
    scope,
    project_id: projectId ?? null,
    roles: roles.length > 0 ? roles : null,
    secrets: Object.keys(chosen).filter((key) => chosen[key] === "secret"),
    variables: Object.keys(chosen).filter((key) => chosen[key] === "variable"),
    skip: skipped,
  });

  const review = (skipped = skip, chosen = kinds): void => {
    setBusy(true);
    setError(null);
    post("/v1/connections/review_env", body(skipped, chosen))
      .then((result) => setLines(result.lines))
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };

  const save = (): void => {
    setBusy(true);
    setError(null);
    post("/v1/connections/import_env", body(skip, kinds))
      .then((result) => {
        setText("");
        onSaved(result.saved);
      })
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };

  const toSave = (lines ?? []).filter((line) => !line.skipped);
  const blocked = toSave.filter((line) => line.problem);
  return (
    <Sheet title={words.importTitle} subtitle={words.importHelp} size="lg" testId="import-env" onClose={onClose}>
      {lines === null ? (
        <form
          className="connection-form"
          autoComplete="off"
          onSubmit={(event) => {
            event.preventDefault();
            review();
          }}
        >
          <div className="field">
            <label htmlFor={id}>{words.importText}</label>
            <textarea
              id={id}
              className="masked env-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={10}
              required
              spellCheck={false}
              autoComplete="off"
              placeholder={"API_KEY=…\nREGION=ca-east"}
            />
          </div>
          {roleOptions ? (
            <RolePicker legend={words.form.rolesLegend} help={words.importRolesHelp} roles={roleOptions} chosen={roles} onChange={setRoles} />
          ) : null}
          <ErrorNote error={error} />
          <div className="form-actions">
            <button type="button" className="button" onClick={onClose}>
              {words.form.cancel}
            </button>
            <button type="submit" className="button primary" disabled={busy || !text.trim()}>
              {busy ? words.reviewing : words.review}
            </button>
          </div>
        </form>
      ) : (
        <>
          <h3 className="group-title">{words.reviewTitle(lines.length)}</h3>
          <div className="table-wrap">
            <table className="import-review" data-testid="import-review">
              <thead>
                <tr>
                  <th scope="col">{words.columns.name}</th>
                  <th scope="col">{words.columns.kind}</th>
                  <th scope="col">{words.columns.skip}</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.line} className={line.skipped ? "skipped" : line.problem ? "has-problem" : ""}>
                    <th scope="row">
                      <code>{line.name}</code>
                      {line.problem && !line.skipped ? <p className="import-problem">{line.problem}</p> : null}
                    </th>
                    <td>
                      <select
                        aria-label={`${words.columns.kind} ${line.name}`}
                        value={line.kind}
                        disabled={line.skipped}
                        onChange={(event) => {
                          const chosen = { ...kinds, [line.name]: event.target.value };
                          setKinds(chosen);
                          setLines(lines.map((other) => (other.name === line.name ? { ...other, kind: event.target.value } : other)));
                          review(skip, chosen);
                        }}
                      >
                        <option value="secret">{words.kinds.secret}</option>
                        <option value="variable">{words.kinds.variable}</option>
                      </select>
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`${words.columns.skip} ${line.name}`}
                        checked={line.skipped}
                        onChange={() => {
                          const skipped = line.skipped ? skip.filter((key) => key !== line.name) : [...skip, line.name];
                          setSkip(skipped);
                          // Shown at once; the review that follows brings the line's problem back, if any.
                          setLines(lines.map((other) => (other.name === line.name ? { ...other, skipped: !line.skipped } : other)));
                          review(skipped, kinds);
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {blocked.length > 0 ? (
            <p className="note note-warning" role="status">
              {words.importProblems(blocked.length)}
            </p>
          ) : null}
          <ErrorNote error={error} />
          <div className="form-actions">
            <button type="button" className="button" onClick={() => setLines(null)} disabled={busy}>
              {words.importBack}
            </button>
            <button
              type="button"
              className="button primary"
              onClick={save}
              disabled={busy || blocked.length > 0 || toSave.length === 0}
            >
              {busy ? words.form.saving : words.importSave(toSave.length)}
            </button>
          </div>
        </>
      )}
    </Sheet>
  );
}
