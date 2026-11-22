/** Settings: each with its current value and allowed range; change one, with a reason for project settings. */
import { useState, type FormEvent } from "react";
import { get, post, type Schemas } from "../api/client";
import { ErrorNote, Loading } from "../components/common";
import { formatValue } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { ApprovedClients } from "./ApprovedClients";

type Setting = Schemas["SettingItem"];
type View = Schemas["SettingsView"];
type Value = string | number | boolean;

/** Keeps the value's type: a setting that holds a number is sent as a number when the text is one. */
function typedValue(current: unknown, text: string): Value {
  const trimmed = text.trim();
  if (typeof current === "number" && trimmed !== "" && Number.isFinite(Number(trimmed))) return Number(trimmed);
  if (typeof current === "boolean" && (trimmed === "true" || trimmed === "false")) return trimmed === "true";
  return trimmed;
}

function ChangeForm({
  setting,
  needsReason,
  onSave,
  onCancel,
}: {
  setting: Setting;
  needsReason: boolean;
  onSave(value: Value, reason: string): Promise<void>;
  onCancel(): void;
}): JSX.Element {
  const [value, setValue] = useState(formatValue(setting.value));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const id = `setting-${setting.name}`;

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSave(typedValue(setting.value, value), reason);
    } catch (reason_) {
      setError(reason_);
      setBusy(false);
    }
  };

  return (
    <form className="setting-form" onSubmit={(event) => void submit(event)}>
      <label htmlFor={`${id}-value`}>{t.settings.newValue(setting.name)}</label>
      <input
        id={`${id}-value`}
        value={value}
        autoFocus
        aria-describedby={`${id}-allowed`}
        onChange={(event) => setValue(event.target.value)}
      />
      {needsReason ? (
        <>
          <label htmlFor={`${id}-reason`}>{t.settings.reason}</label>
          <input id={`${id}-reason`} value={reason} onChange={(event) => setReason(event.target.value)} />
        </>
      ) : null}
      <ErrorNote error={error} />
      <div className="row">
        <button type="submit" className="button primary small" disabled={busy}>
          {t.settings.save}
        </button>
        <button type="button" className="button small" onClick={onCancel}>
          {t.common.cancel}
        </button>
      </div>
    </form>
  );
}

function SettingsList({
  title,
  view,
  needsReason,
  onSave,
}: {
  title: string;
  view: View;
  needsReason: boolean;
  onSave(name: string, value: Value, reason: string): Promise<void>;
}): JSX.Element {
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      <ul className="settings plain">
        {view.items.map((setting) => (
          <li key={setting.name} data-testid={`setting-${setting.name}`}>
            <div className="setting-line">
              <span className="setting-name">{setting.name}</span>
              <span className="setting-value">{formatValue(setting.value)}</span>
              <button
                type="button"
                className="link"
                aria-expanded={editing === setting.name}
                onClick={() => setEditing(editing === setting.name ? null : setting.name)}
              >
                {t.settings.change}
                <span className="visually-hidden"> {setting.name}</span>
              </button>
            </div>
            <p className="quiet" id={`setting-${setting.name}-allowed`}>
              {t.settings.allowed(setting.allowed, setting.unit)}
            </p>
            {editing === setting.name ? (
              <ChangeForm
                setting={setting}
                needsReason={needsReason}
                onCancel={() => setEditing(null)}
                onSave={async (value, reason) => {
                  await onSave(setting.name, value, reason);
                  setEditing(null);
                }}
              />
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function SettingsPanel({ projectId, changes }: { projectId: string; changes: number }): JSX.Element {
  const project = useLoad(() => get("/v1/settings/show_project", { project_id: projectId }), [projectId, changes]);
  const mine = useLoad(() => get("/v1/settings/show_mine"), []);
  return (
    <>
      <ErrorNote error={project.error} />
      <ErrorNote error={mine.error} />
      {(project.loading && !project.data) || (mine.loading && !mine.data) ? <Loading /> : null}
      {project.data ? (
        <SettingsList
          title={t.settings.project}
          view={project.data}
          needsReason
          onSave={async (name, value, reason) => {
            project.setData(
              await post("/v1/settings/change_project", { project_id: projectId, changes: { [name]: value }, reason }),
            );
          }}
        />
      ) : null}
      {mine.data ? (
        <SettingsList
          title={t.settings.mine}
          view={mine.data}
          needsReason={false}
          onSave={async (name, value) => {
            mine.setData(await post("/v1/settings/change_mine", { changes: { [name]: value } }));
          }}
        />
      ) : null}
      <ApprovedClients />
    </>
  );
}
