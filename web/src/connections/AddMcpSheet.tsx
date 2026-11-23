/**
 * Adding a remote MCP server (CON-9, CON-10, CON-15): its address, how crewmind signs in (four
 * cards, each showing only its fields), a test that lists the server's tools before anything is
 * saved, and for OAuth a sign-in at the provider right after saving. A token or header value
 * lives only in its field, never in React state or the page's markup.
 */
import { useId, useRef, useState, type FormEvent } from "react";
import { Globe, KeyRound, LogIn, Tag } from "lucide-react";
import { post, type Schemas } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { ChoiceCard } from "../settings/ChoiceCard";
import { connectionWords } from "../strings.connections";
import { Pill } from "../ui/Status";
import { Sheet } from "../ui/Sheet";
import type { AddContext } from "./AddSheet";
import { RolePicker } from "./RolePicker";

type Item = Schemas["ConnectionView"];
type Probe = Schemas["ProbeView"];
type Auth = "none" | "bearer" | "header" | "oauth";

const words = connectionWords;
const ICONS: Record<Auth, JSX.Element> = {
  none: <Globe size={18} />,
  bearer: <KeyRound size={18} />,
  header: <Tag size={18} />,
  oauth: <LogIn size={18} />,
};

interface Props {
  context: AddContext;
  name?: string;
  roles?: string[];
  onClose(): void;
  onSaved(item: Item): void;
}

export function AddMcpSheet({ context, name: presetName, roles: presetRoles, onClose, onSaved }: Props): JSX.Element {
  const id = useId();
  const field = (part: string): string => `${id}-${part}`;
  const { person } = useAuth();
  const inProject = context.mode === "project";
  const [name, setName] = useState(presetName ?? "");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [auth, setAuth] = useState<Auth>("none");
  const [headerName, setHeaderName] = useState("");
  const valueField = useRef<HTMLInputElement>(null);
  const [clientId, setClientId] = useState("");
  const clientSecret = useRef<HTMLInputElement>(null);
  const [privateNetwork, setPrivateNetwork] = useState(false);
  const [scope, setScope] = useState<"person" | "install" | "project">(context.mode === "project" ? "project" : context.scope);
  const [roles, setRoles] = useState<string[]>(presetRoles ?? []);
  const [probe, setProbe] = useState<Probe | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | null>(null);
  const [error, setError] = useState<unknown>(null);

  const target = () => ({
    url: url.trim(),
    auth_kind: auth,
    header_name: auth === "header" ? headerName.trim() : null,
    value: auth === "bearer" || auth === "header" ? (valueField.current?.value ?? "") : null,
    private_network: privateNetwork,
  });

  const changed = (): void => setProbe(null);

  const test = (): void => {
    setBusy("test");
    setError(null);
    post("/v1/connections/test_mcp_server", target())
      .then(setProbe)
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(null));
  };

  const save = (event: FormEvent): void => {
    event.preventDefault();
    setBusy("save");
    setError(null);
    post("/v1/connections/add_mcp_server", {
      ...target(),
      name: name.trim(),
      description: description.trim(),
      scope,
      project_id: inProject ? context.projectId : null,
      roles: inProject && roles.length > 0 ? roles : null,
    })
      .then(async (item) => {
        if (valueField.current) valueField.current.value = "";
        if (auth !== "oauth") {
          onSaved(item);
          return;
        }
        const started = await post("/v1/connections/sign_in", {
          connection: item.id,
          project_id: inProject ? context.projectId : null,
          client_id: clientId.trim() || null,
          client_secret: clientSecret.current?.value || null,
        });
        window.location.assign(started.authorize_url);
      })
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(null));
  };

  const canSave = auth === "oauth" || probe !== null;
  return (
    <Sheet title={words.mcp.addTitle} size="lg" testId="add-mcp" onClose={onClose}>
      <form className="connection-form" onSubmit={save} autoComplete="off">
        <div className="field">
          <label htmlFor={field("name")}>{words.form.name}</label>
          <input id={field("name")} value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} spellCheck={false} readOnly={Boolean(presetName)} />
        </div>
        <div className="field">
          <label htmlFor={field("description")}>{words.form.description}</label>
          <input id={field("description")} value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={300} aria-describedby={field("description-help")} />
          <p className="quiet" id={field("description-help")}>
            {words.form.descriptionHelp}
          </p>
        </div>
        <div className="field">
          <label htmlFor={field("url")}>{words.mcp.url}</label>
          <input
            id={field("url")}
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              changed();
            }}
            required
            spellCheck={false}
            placeholder="https://mcp.example.com/mcp"
            aria-describedby={field("url-help")}
          />
          <p className="quiet" id={field("url-help")}>
            {words.mcp.urlHelp}
          </p>
        </div>
        <fieldset className="choice-cards compact">
          <legend>{words.mcp.authLegend}</legend>
          {(["none", "bearer", "header", "oauth"] as const).map((option) => (
            <ChoiceCard
              key={option}
              name={field("auth")}
              value={option}
              checked={auth === option}
              onChange={() => {
                setAuth(option);
                changed();
              }}
              title={words.mcp.auth[option]?.title ?? option}
              help={words.mcp.auth[option]?.help}
              icon={ICONS[option]}
            />
          ))}
        </fieldset>
        {auth === "header" ? (
          <div className="field">
            <label htmlFor={field("header")}>{words.form.headerName}</label>
            <input id={field("header")} value={headerName} onChange={(e) => { setHeaderName(e.target.value); changed(); }} required spellCheck={false} placeholder="X-Api-Key" />
          </div>
        ) : null}
        {auth === "bearer" || auth === "header" ? (
          <div className="field">
            <label htmlFor={field("value")}>{auth === "bearer" ? words.mcp.token : words.mcp.headerValue}</label>
            <input
              id={field("value")}
              ref={valueField}
              type="password"
              required
              autoComplete="new-password"
              spellCheck={false}
              data-1p-ignore
              data-lpignore="true"
              onInput={changed}
              aria-describedby={field("value-help")}
            />
            <p className="quiet" id={field("value-help")}>
              {words.form.valueHelp}
            </p>
          </div>
        ) : null}
        {auth === "oauth" ? (
          <>
            <p className="note note-info small">{words.mcp.oauthNote}</p>
            <details className="field">
              <summary>{words.mcp.clientLegend}</summary>
              <label htmlFor={field("client")}>{words.mcp.clientId}</label>
              <input id={field("client")} value={clientId} onChange={(e) => setClientId(e.target.value)} spellCheck={false} />
              <label htmlFor={field("client-secret")}>{words.mcp.clientSecret}</label>
              <input id={field("client-secret")} ref={clientSecret} type="password" autoComplete="new-password" spellCheck={false} data-1p-ignore />
            </details>
          </>
        ) : null}
        {person?.role === "admin" ? (
          <div className="check-row">
            <input
              id={field("private")}
              type="checkbox"
              checked={privateNetwork}
              onChange={(e) => {
                setPrivateNetwork(e.target.checked);
                changed();
              }}
            />
            <label htmlFor={field("private")}>
              <strong>{words.mcp.privateNetwork}</strong>
              <span className="quiet small"> {words.mcp.privateHelp}</span>
            </label>
          </div>
        ) : null}

        {auth !== "oauth" ? (
          <div className="mcp-test">
            <button type="button" className="button" onClick={test} disabled={busy !== null || !url.trim()}>
              {busy === "test" ? words.mcp.testing : words.mcp.test}
            </button>
            {probe ? (
              <div className="note note-success" role="status" data-testid="mcp-probe">
                <p className="note-title">{words.mcp.tested(probe.server_name ?? url, probe.tools.length)}</p>
                <ul className="plain mcp-probe-tools">
                  {probe.tools.map((tool) => (
                    <li key={tool.name}>
                      <code>{tool.name}</code>{" "}
                      <Pill tone={tool.reads_only ? "neutral" : "warning"} dot={false}>
                        {tool.reads_only ? words.mcp.reads : words.mcp.changes}
                      </Pill>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="quiet small">{words.mcp.testFirst}</p>
            )}
          </div>
        ) : null}

        {inProject ? (
          <>
            <fieldset className="choice-cards compact">
              <legend>{words.form.scopeLegend}</legend>
              {(["project", "person"] as const).map((option) => (
                <ChoiceCard key={option} name={field("scope")} value={option} checked={scope === option} onChange={() => setScope(option)} title={words.scopes[option]} help={words.scopeHelp[option]} />
              ))}
            </fieldset>
            <RolePicker legend={words.form.rolesLegend} roles={context.roles} chosen={roles} onChange={setRoles} />
          </>
        ) : null}
        <ErrorNote error={error} />
        <div className="form-actions">
          <button type="button" className="button" onClick={onClose} disabled={busy !== null}>
            {words.form.cancel}
          </button>
          <button type="submit" className="button primary" disabled={busy !== null || !canSave || (inProject && roles.length === 0)}>
            {busy === "save" ? words.form.saving : auth === "oauth" ? words.mcp.saveAndSignIn : words.form.save}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
