/**
 * One flow to add a secret or a variable (CON-2, CON-3, CON-15). Opened from Settings or a
 * project, optionally pre-filled with a need ("wordpress, for blog-writer"). The value is typed
 * into a field that is never pre-filled, never stored in the browser, and gone once saved.
 */
import { useId, useRef, useState, type FormEvent } from "react";
import { Braces, KeyRound, Send } from "lucide-react";
import { post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { ChoiceCard } from "../settings/ChoiceCard";
import { connectionWords as words } from "../strings.connections";
import { Sheet } from "../ui/Sheet";
import { RolePicker } from "./RolePicker";

type Item = Schemas["ConnectionView"];
type Role = Schemas["RoleOption"];
type Kind = "secret" | "variable";
type Delivery = "sent_for_you" | "given";
type HeaderKind = "bearer" | "basic" | "header";

export type AddContext =
  | { mode: "settings"; scope: "person" | "install" }
  | { mode: "project"; projectId: string; roles: Role[] };

export interface Preset {
  kind: Kind;
  name: string;
  roles: string[];
}

interface Props {
  context: AddContext;
  preset?: Preset;
  startKind?: Kind;
  onClose(): void;
  onSaved(item: Item): void;
}

function sitesOf(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((site) => site.trim())
    .filter(Boolean);
}

export function AddSheet({ context, preset, startKind = "secret", onClose, onSaved }: Props): JSX.Element {
  const id = useId();
  const [kind, setKind] = useState<Kind>(preset?.kind ?? startKind);
  const [name, setName] = useState(preset?.name ?? "");
  const [description, setDescription] = useState("");
  const [delivery, setDelivery] = useState<Delivery>("sent_for_you");
  const [sites, setSites] = useState("");
  const [headerKind, setHeaderKind] = useState<HeaderKind>("bearer");
  const [headerName, setHeaderName] = useState("");
  const [basicUser, setBasicUser] = useState("");
  const [shape, setShape] = useState<"text" | "file">("text");
  const [envName, setEnvName] = useState("");
  // The value lives only in the field, never in React state or a DOM attribute (CON-15).
  const valueField = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const [variableValue, setVariableValue] = useState("");
  const [shown, setShown] = useState(false);
  const [expires, setExpires] = useState("");
  const inProject = context.mode === "project";
  const [scope, setScope] = useState<"person" | "install" | "project">(
    context.mode === "project" ? "project" : context.scope,
  );
  const [roles, setRoles] = useState<string[]>(preset?.roles ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const field = (part: string): string => `${id}-${part}`;
  const defaultEnv = name.replace(/[^A-Za-z0-9_]/g, "_").toUpperCase();

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const value = kind === "secret" ? (valueField.current?.value ?? "") : variableValue;
    const placement = {
      scope,
      project_id: inProject ? context.projectId : null,
      roles: inProject && roles.length > 0 ? roles : null,
    };
    const saving =
      kind === "secret"
        ? post("/v1/connections/add_secret", {
            ...placement,
            name: name.trim(),
            description: description.trim(),
            value,
            delivery,
            sites: delivery === "sent_for_you" ? sitesOf(sites) : [],
            header_kind: headerKind,
            header_name: headerKind === "header" ? headerName.trim() : null,
            basic_user: headerKind === "basic" ? basicUser.trim() : null,
            shape,
            env_name: delivery === "given" && envName.trim() ? envName.trim() : null,
            expires_on: expires || null,
          })
        : post("/v1/connections/add_variable", {
            ...placement,
            name: name.trim(),
            description: description.trim(),
            value,
            env_name: envName.trim() || null,
          });
    saving
      .then((item) => {
        if (valueField.current) valueField.current.value = "";
        onSaved(item);
      })
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };

  const title = preset ? `${words.add} ${preset.name}` : kind === "secret" ? words.addSecret : words.addVariable;
  return (
    <Sheet title={title} size="lg" testId="add-connection" onClose={onClose}>
      <form className="connection-form" onSubmit={submit} autoComplete="off">
        {preset ? null : (
          <fieldset className="choice-cards compact">
            <legend>{words.form.kindLegend}</legend>
            <ChoiceCard
              name={field("kind")}
              value="secret"
              checked={kind === "secret"}
              onChange={() => setKind("secret")}
              title={words.kinds.secret}
              icon={<KeyRound size={18} />}
            />
            <ChoiceCard
              name={field("kind")}
              value="variable"
              checked={kind === "variable"}
              onChange={() => setKind("variable")}
              title={words.kinds.variable}
              icon={<Braces size={18} />}
            />
          </fieldset>
        )}
        <div className="field">
          <label htmlFor={field("name")}>{words.form.name}</label>
          <input
            id={field("name")}
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            maxLength={100}
            spellCheck={false}
            aria-describedby={field("name-help")}
            readOnly={Boolean(preset)}
          />
          <p className="quiet" id={field("name-help")}>
            {words.form.nameHelp}
          </p>
        </div>
        <div className="field">
          <label htmlFor={field("description")}>{words.form.description}</label>
          <input
            id={field("description")}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            required
            maxLength={300}
            aria-describedby={field("description-help")}
          />
          <p className="quiet" id={field("description-help")}>
            {words.form.descriptionHelp}
          </p>
        </div>

        {kind === "secret" ? (
          <>
            <fieldset className="choice-cards compact">
              <legend>{words.form.useLegend}</legend>
              <ChoiceCard
                name={field("delivery")}
                value="sent_for_you"
                checked={delivery === "sent_for_you"}
                onChange={() => setDelivery("sent_for_you")}
                title={words.form.sendTitle}
                help={words.form.sendHelp}
                icon={<Send size={18} />}
              />
              <ChoiceCard
                name={field("delivery")}
                value="given"
                checked={delivery === "given"}
                onChange={() => setDelivery("given")}
                title={words.form.giveTitle}
                help={words.form.giveHelp}
                icon={<KeyRound size={18} />}
              />
            </fieldset>
            {delivery === "sent_for_you" ? (
              <>
                <div className="field">
                  <label htmlFor={field("sites")}>{words.form.sites}</label>
                  <input
                    id={field("sites")}
                    value={sites}
                    onChange={(event) => setSites(event.target.value)}
                    required
                    spellCheck={false}
                    placeholder="example.com"
                    aria-describedby={field("sites-help")}
                  />
                  <p className="quiet" id={field("sites-help")}>
                    {words.form.sitesHelp}
                  </p>
                </div>
                <fieldset>
                  <legend>{words.form.authLegend}</legend>
                  <div className="segmented" role="radiogroup" aria-label={words.form.authLegend}>
                    {(["bearer", "basic", "header"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        role="radio"
                        aria-checked={headerKind === option}
                        className={headerKind === option ? "active" : ""}
                        onClick={() => setHeaderKind(option)}
                      >
                        {words.form[option]}
                      </button>
                    ))}
                  </div>
                  {headerKind === "header" ? (
                    <div className="field nested">
                      <label htmlFor={field("header")}>{words.form.headerName}</label>
                      <input
                        id={field("header")}
                        value={headerName}
                        onChange={(event) => setHeaderName(event.target.value)}
                        required
                        spellCheck={false}
                        placeholder="X-Api-Key"
                      />
                    </div>
                  ) : null}
                  {headerKind === "basic" ? (
                    <div className="field nested">
                      <label htmlFor={field("user")}>{words.form.basicUser}</label>
                      <input
                        id={field("user")}
                        value={basicUser}
                        onChange={(event) => setBasicUser(event.target.value)}
                        required
                        spellCheck={false}
                      />
                    </div>
                  ) : null}
                </fieldset>
                <p className="quiet small">{words.form.pinnedWarning}</p>
              </>
            ) : (
              <>
                <p className="note note-warning small">{words.form.giveCaveat}</p>
                <fieldset>
                  <legend>{words.form.shapeLegend}</legend>
                  <div className="segmented" role="radiogroup" aria-label={words.form.shapeLegend}>
                    {(["text", "file"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        role="radio"
                        aria-checked={shape === option}
                        className={shape === option ? "active" : ""}
                        onClick={() => setShape(option)}
                      >
                        {words.form[option]}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <div className="field">
                  <label htmlFor={field("env")}>{shape === "file" ? words.form.fileName : words.form.envName}</label>
                  <input
                    id={field("env")}
                    value={envName}
                    onChange={(event) => setEnvName(event.target.value)}
                    placeholder={defaultEnv}
                    spellCheck={false}
                    aria-describedby={field("env-help")}
                  />
                  <p className="quiet" id={field("env-help")}>
                    {words.form.envHelp}
                  </p>
                </div>
              </>
            )}
          </>
        ) : (
          <div className="field">
            <label htmlFor={field("env")}>{words.form.envName}</label>
            <input
              id={field("env")}
              value={envName}
              onChange={(event) => setEnvName(event.target.value)}
              placeholder={defaultEnv}
              spellCheck={false}
            />
          </div>
        )}

        <div className="field">
          <label htmlFor={field("value")}>{kind === "secret" ? words.form.value : words.form.valueVariable}</label>
          <div className="secret-input">
            {kind === "variable" ? (
              <input
                id={field("value")}
                value={variableValue}
                onChange={(event) => setVariableValue(event.target.value)}
                required
                spellCheck={false}
                autoComplete="off"
                aria-describedby={field("value-help")}
              />
            ) : shape === "file" && delivery === "given" ? (
              <textarea
                id={field("value")}
                ref={(element) => {
                  valueField.current = element;
                }}
                required
                rows={5}
                spellCheck={false}
                autoComplete="off"
                className={shown ? "" : "masked"}
                aria-describedby={field("value-help")}
              />
            ) : (
              <input
                id={field("value")}
                ref={(element) => {
                  valueField.current = element;
                }}
                type={shown ? "text" : "password"}
                required
                spellCheck={false}
                autoComplete="new-password"
                data-1p-ignore
                data-lpignore="true"
                aria-describedby={field("value-help")}
              />
            )}
            {kind === "secret" ? (
              <button type="button" className="button small ghost" aria-pressed={shown} onClick={() => setShown(!shown)}>
                {shown ? words.form.hide : words.form.show}
              </button>
            ) : null}
          </div>
          <p className="quiet" id={field("value-help")}>
            {kind === "secret" ? words.form.valueHelp : words.form.variableHelp}
          </p>
        </div>

        {kind === "secret" ? (
          <div className="field">
            <label htmlFor={field("expires")}>{words.form.expires}</label>
            <input
              id={field("expires")}
              type="date"
              value={expires}
              onChange={(event) => setExpires(event.target.value)}
              aria-describedby={field("expires-help")}
            />
            <p className="quiet" id={field("expires-help")}>
              {words.form.expiresHelp}
            </p>
          </div>
        ) : null}

        {inProject ? (
          <fieldset className="choice-cards compact">
            <legend>{words.form.scopeLegend}</legend>
            {(["project", "person"] as const).map((option) => (
              <ChoiceCard
                key={option}
                name={field("scope")}
                value={option}
                checked={scope === option}
                onChange={() => setScope(option)}
                title={words.scopes[option]}
                help={words.scopeHelp[option]}
              />
            ))}
          </fieldset>
        ) : null}

        {inProject ? (
          <RolePicker
            legend={words.form.rolesLegend}
            help={preset && preset.roles.length > 0 ? words.form.rolesNeeded : undefined}
            roles={context.roles}
            chosen={roles}
            onChange={setRoles}
          />
        ) : null}

        <ErrorNote error={error} />
        <div className="form-actions">
          <button type="button" className="button" onClick={onClose} disabled={busy}>
            {words.form.cancel}
          </button>
          <button
            type="submit"
            className="button primary"
            disabled={busy || (inProject && roles.length === 0 && !(preset && preset.roles.length > 0))}
          >
            {busy ? words.form.saving : words.form.save}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
