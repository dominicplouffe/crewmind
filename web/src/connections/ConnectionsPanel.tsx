/**
 * A project's connections (CON-4, CON-5, CON-14, CON-15). It leads with what the squad needs and
 * lacks, each with Add in place, pre-filled with the need; then what is attached, with who may
 * use it as chips edited in place; then what is ready to attach.
 */
import { useState } from "react";
import { AlertTriangle, ClipboardPaste, Plus } from "lucide-react";
import { get, post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { connectionWords as words, kindWord } from "../strings.connections";
import { Skeleton } from "../ui/Skeleton";
import { AddSheet, type Preset } from "./AddSheet";
import { EmptyKinds } from "./ConnectionsSection";
import { ImportSheet } from "./ImportSheet";
import { ItemRow } from "./ItemRow";
import { RolePicker } from "./RolePicker";

type Attached = Schemas["Attached"];
type Item = Schemas["ConnectionView"];
type Need = Schemas["NeedView"];
type Role = Schemas["RoleOption"];

interface Props {
  projectId: string;
  changes: number;
  onChanged(): void;
}

function kindOf(kind: string): "secret" | "variable" | "mcp_server" {
  return kind === "variable" || kind === "mcp_server" ? kind : "secret";
}

function roleNames(slugs: string[], roles: Role[]): string[] {
  if (slugs.includes("*")) return [words.project.allRoles];
  return slugs.map((slug) => roles.find((role) => role.slug === slug)?.name ?? slug);
}

function NeedRow({ need, roles, onAdd }: { need: Need; roles: Role[]; onAdd(): void }): JSX.Element {
  const kind = kindWord(need.kind).toLowerCase();
  return (
    <li className="need-row" data-testid="need-missing">
      <AlertTriangle size={18} aria-hidden="true" className="need-icon" />
      <div className="need-main">
        <p className="need-name">
          <span>{need.name}</span>
          <span className="quiet small"> · {kind}</span>
          {need.state === "waived" ? <span className="quiet small"> · {words.project.waived}</span> : null}
        </p>
        <p className="quiet small">{words.project.needFor(roleNames(need.roles, roles))}</p>
        {need.seats.length > 0 ? <p className="small need-waits">{words.project.waits(need.seats)}</p> : null}
      </div>
      <button type="button" className="button small primary" onClick={onAdd}>
        <Plus size={16} aria-hidden="true" />
        {words.project.addIt(kind)}
        <span className="visually-hidden"> {need.name}</span>
      </button>
    </li>
  );
}

function Grants({
  projectId,
  attached,
  roles,
  onChanged,
}: {
  projectId: string;
  attached: Attached;
  roles: Role[];
  onChanged(): void;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [chosen, setChosen] = useState<string[]>(attached.roles);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!editing) {
    return (
      <div className="grants">
        <span className="quiet small">{words.project.grants}:</span>
        <ul className="chips plain" aria-label={words.project.grants}>
          {roleNames(attached.roles, roles).map((name) => (
            <li key={name} className="chip chip-on">
              {name}
            </li>
          ))}
        </ul>
        <button type="button" className="button small ghost" onClick={() => setEditing(true)}>
          {words.edit}
          <span className="visually-hidden"> {words.project.editGrants(attached.item.name)}</span>
        </button>
      </div>
    );
  }
  const save = (): void => {
    setBusy(true);
    setError(null);
    post("/v1/connections/set_grants", { project_id: projectId, connection: attached.item.id, roles: chosen })
      .then(() => {
        setEditing(false);
        onChanged();
      })
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };
  return (
    <div className="grants editing">
      <RolePicker legend={words.project.editGrants(attached.item.name)} roles={roles} chosen={chosen} onChange={setChosen} />
      <ErrorNote error={error} />
      <div className="row">
        <button type="button" className="button small" onClick={() => setEditing(false)} disabled={busy}>
          {words.form.cancel}
        </button>
        <button type="button" className="button small primary" onClick={save} disabled={busy || chosen.length === 0}>
          {words.project.saveGrants}
        </button>
      </div>
    </div>
  );
}

function AttachRow({
  projectId,
  item,
  roles,
  needed,
  onChanged,
}: {
  projectId: string;
  item: Item;
  roles: Role[];
  /** A role declared a need this item meets, so the server grants those roles by default. */
  needed: boolean;
  onChanged(): void;
}): JSX.Element {
  const [choosing, setChoosing] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const attach = (granted: string[] | null): void => {
    setBusy(true);
    setError(null);
    post("/v1/connections/attach", { project_id: projectId, connection: item.id, roles: granted, env_name: null })
      .then(onChanged)
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };
  return (
    <ItemRow
      item={item}
      onChanged={onChanged}
      actions={
        choosing ? null : (
          <button
            type="button"
            className="button small"
            onClick={() => (needed ? attach(null) : setChoosing(true))}
            disabled={busy}
          >
            {words.project.attach}
            <span className="visually-hidden"> {item.name}</span>
          </button>
        )
      }
    >
      {choosing ? (
        <div className="grants editing">
          <RolePicker legend={words.form.rolesLegend} roles={roles} chosen={chosen} onChange={setChosen} />
          <div className="row">
            <button type="button" className="button small" onClick={() => setChoosing(false)} disabled={busy}>
              {words.form.cancel}
            </button>
            <button
              type="button"
              className="button small primary"
              onClick={() => attach(chosen)}
              disabled={busy || chosen.length === 0}
            >
              {words.project.attach}
            </button>
          </div>
        </div>
      ) : null}
      <ErrorNote error={error} />
    </ItemRow>
  );
}

export function ConnectionsPanel({ projectId, changes, onChanged }: Props): JSX.Element {
  const [tick, setTick] = useState(0);
  const view = useLoad(() => get("/v1/connections/for_project", { project_id: projectId }), [projectId, changes, tick]);
  const [adding, setAdding] = useState<{ kind: "secret" | "variable" | "mcp_server"; preset?: Preset } | null>(null);
  const [importing, setImporting] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const changed = (message?: string): void => {
    setSaved(message ?? null);
    setActionError(null);
    setTick((value) => value + 1);
    onChanged();
  };
  const data = view.data;
  const roles = data?.roles ?? [];
  const missing = (data?.needs ?? []).filter((need) => need.state !== "met");
  const nothing = data && data.attached.length === 0 && missing.length === 0 && data.available.length === 0;

  return (
    <div className="connections-panel" data-testid="connections-panel">
      <ErrorNote error={view.error} />
      <ErrorNote error={actionError} />
      {view.loading && !data ? <Skeleton lines={4} block /> : null}
      {saved ? (
        <p className="note note-success" role="status">
          {saved}
        </p>
      ) : null}
      {missing.length > 0 ? (
        <section className="connections-group missing" aria-labelledby="missing-title">
          <h3 id="missing-title" className="group-title">
            {words.project.missingTitle}
          </h3>
          <p className="quiet small">{words.project.missingHelp}</p>
          <ul className="plain need-list">
            {missing.map((need) => (
              <NeedRow
                key={`${need.kind}:${need.name}`}
                need={need}
                roles={roles}
                onAdd={() =>
                  setAdding({
                    kind: kindOf(need.kind),
                    preset: { kind: kindOf(need.kind), name: need.name, roles: need.roles },
                  })
                }
              />
            ))}
          </ul>
        </section>
      ) : null}
      {data ? (
        <section className="connections-group" aria-labelledby="attached-title">
          <div className="group-head">
            <h3 id="attached-title" className="group-title">
              {words.project.attachedTitle}
            </h3>
            <div className="row">
              <button type="button" className="button small" onClick={() => setImporting(true)}>
                <ClipboardPaste size={16} aria-hidden="true" />
                {words.pasteEnv}
              </button>
              <button type="button" className="button small primary" onClick={() => setAdding({ kind: "secret" })}>
                <Plus size={16} aria-hidden="true" />
                {words.add}
              </button>
            </div>
          </div>
          {nothing ? <EmptyKinds onAdd={(kind) => setAdding({ kind })} /> : null}
          {!nothing && data.attached.length === 0 ? <p className="quiet">{words.project.attachedEmpty}</p> : null}
          <ul className="connection-list plain">
            {data.attached.map((attached) => (
              <ItemRow
                key={attached.item.id}
                item={attached.item}
                onChanged={() => changed()}
                extraMenu={[
                  {
                    key: "detach",
                    label: words.project.detach,
                    run: () => {
                      void post("/v1/connections/detach", { project_id: projectId, connection: attached.item.id })
                        .then(() => changed())
                        .catch((reason: unknown) => setActionError(reason));
                    },
                  },
                ]}
              >
                <Grants projectId={projectId} attached={attached} roles={roles} onChanged={() => changed()} />
              </ItemRow>
            ))}
          </ul>
        </section>
      ) : null}
      {data && data.available.length > 0 ? (
        <section className="connections-group" aria-labelledby="available-title">
          <h3 id="available-title" className="group-title">
            {words.project.availableTitle}
          </h3>
          <p className="quiet small">{words.project.availableHelp}</p>
          <ul className="connection-list plain">
            {data.available.map((item) => (
              <AttachRow
                key={item.id}
                projectId={projectId}
                item={item}
                roles={roles}
                needed={(data.needs ?? []).some(
                  (need) => need.kind === item.kind && need.name.toLowerCase() === item.name.toLowerCase(),
                )}
                onChanged={() => changed(words.attached(item.name))}
              />
            ))}
          </ul>
        </section>
      ) : null}
      {adding ? (
        <AddSheet
          context={{ mode: "project", projectId, roles }}
          preset={adding.preset}
          startKind={adding.kind}
          onClose={() => setAdding(null)}
          onSaved={(item) => {
            setAdding(null);
            changed(adding.preset ? words.attached(item.name) : words.saved(item.name));
          }}
        />
      ) : null}
      {importing ? (
        <ImportSheet
          scope="project"
          projectId={projectId}
          roleOptions={roles}
          onClose={() => setImporting(false)}
          onSaved={(count) => {
            setImporting(false);
            changed(words.importSaved(count));
          }}
        />
      ) : null}
    </div>
  );
}
