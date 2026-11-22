/**
 * Adds a model key and checks it works (LLM-2, LLM-4, LLM-10): add it, find the models it can
 * use when none were found yet, then make one tiny test call. A failure says what is wrong and
 * how to fix it, with the provider's own words behind "Show technical details".
 */
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import { get, post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { tokens } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { refreshSetupStatus } from "../onboarding/useSetupStatus";
import { settingsWords } from "../strings.settings";

type Credential = Schemas["CredentialItem"];
type Smoke = Schemas["SmokeResult"];
type Provider = Schemas["ProviderItem"];

export interface AddedKey {
  credential: Credential;
  smoke: Smoke | null;
}

interface Props {
  /** Names already taken, to suggest a free one. */
  existingNames: string[];
  /** The key was added (and worked, or the person chose to keep it). */
  onDone(added: AddedKey): void;
  onCancel?(): void;
  autoFocus?: boolean;
}

type Step = "adding" | "lineup" | "smoking";
type Outcome =
  | { kind: "worked"; added: AddedKey }
  | { kind: "failed"; credential: Credential; detail: string; noModels: boolean };

/** Which fix to suggest for a failed test call, from the provider's message. Wording only. */
export function failureKind(detail: string): keyof typeof settingsWords.keyForm.failedFix {
  if (/auth|401|403|api[ _-]?key|permission|unauthori[sz]ed|forbidden/i.test(detail)) return "auth";
  if (/connect|timeout|timed out|resolve|network|unreachable|ssl|dns/i.test(detail)) return "network";
  if (/rate|quota|429|billing|credit|insufficient/i.test(detail)) return "quota";
  if (/not ?found|404|does not exist/i.test(detail)) return "notFound";
  return "other";
}

function shortLabel(provider: Provider | undefined): string {
  return (provider?.label ?? "").replace(/\s*\(.*\)\s*$/, "").trim();
}

function freeName(base: string, taken: string[]): string {
  if (!base) return "";
  if (!taken.includes(base)) return base;
  for (let index = 2; ; index += 1) {
    const name = `${base} ${index}`;
    if (!taken.includes(name)) return name;
  }
}

export function AddKeyForm({ existingNames, onDone, onCancel, autoFocus = false }: Props): JSX.Element {
  const words = settingsWords.keyForm;
  const id = useId();
  const providers = useLoad(() => get("/v1/models/providers"), []);
  const [provider, setProvider] = useState("");
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [key, setKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [step, setStep] = useState<Step | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [technical, setTechnical] = useState(false);
  const [taken, setTaken] = useState<string[]>(existingNames);
  const resultRef = useRef<HTMLDivElement>(null);

  const items = useMemo(() => providers.data?.items ?? [], [providers.data]);
  const chosen = items.find((item) => item.name === provider);

  useEffect(() => setTaken((current) => Array.from(new Set([...current, ...existingNames]))), [existingNames]);

  // Pick a first provider once the list arrives.
  useEffect(() => {
    const first = items.find((item) => item.name === "anthropic") ?? items[0];
    if (provider || !first) return;
    setProvider(first.name);
  }, [items, provider]);

  // Suggest a name from the provider until the person types their own.
  useEffect(() => {
    if (!nameEdited) setName(freeName(shortLabel(chosen), taken));
  }, [chosen, nameEdited, taken]);

  useEffect(() => {
    if (outcome) resultRef.current?.focus();
  }, [outcome]);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setOutcome(null);
    let credential: Credential;
    try {
      setStep("adding");
      credential = await post("/v1/credentials/add", {
        name: name.trim(),
        provider,
        key: key.trim(),
        base_url: chosen?.needs_base_url ? baseUrl.trim() || null : null,
      });
      setTaken((current) => [...current, credential.name]);
      refreshSetupStatus();
    } catch (reason) {
      setError(reason);
      setStep(null);
      return;
    }
    try {
      if (Object.keys(credential.lineup).length === 0) {
        setStep("lineup");
        credential = await post("/v1/credentials/refresh_lineup", { name: credential.name }).catch(() => credential);
      }
      if (Object.keys(credential.lineup).length === 0) {
        setOutcome({ kind: "failed", credential, detail: "", noModels: true });
        return;
      }
      setStep("smoking");
      const smoke = await post("/v1/credentials/smoke", { name: credential.name });
      if (smoke.ok) {
        const added = { credential, smoke };
        setOutcome({ kind: "worked", added });
        setKey("");
        onDone(added);
      } else {
        setOutcome({ kind: "failed", credential, detail: smoke.detail, noModels: false });
      }
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : String(reason);
      setOutcome({ kind: "failed", credential, detail, noModels: /no model/i.test(detail) });
    } finally {
      setStep(null);
    }
  };

  const removeAndRetry = async (credential: Credential): Promise<void> => {
    setError(null);
    try {
      await post("/v1/credentials/delete", { name: credential.name });
      setTaken((current) => current.filter((item) => item !== credential.name));
      refreshSetupStatus();
      setOutcome(null);
      setKey("");
      window.setTimeout(() => document.getElementById(`${id}-key`)?.focus(), 0);
    } catch (reason) {
      setError(reason);
    }
  };

  if (outcome?.kind === "failed") {
    const fix = outcome.noModels ? words.noModelsFix : words.failedFix[failureKind(outcome.detail)];
    return (
      <div className="key-result note note-error" ref={resultRef} tabIndex={-1} role="alert">
        <p className="note-title">
          <CircleAlert size={16} aria-hidden="true" /> {outcome.noModels ? words.noModels : words.failed}
        </p>
        <p className="note-hint">{fix}</p>
        {outcome.detail ? (
          <>
            <button type="button" className="link" aria-expanded={technical} onClick={() => setTechnical(!technical)}>
              {words.details}
            </button>
            {technical ? <pre className="key-detail">{outcome.detail}</pre> : null}
          </>
        ) : null}
        <ErrorNote error={error} />
        <div className="note-actions">
          <button type="button" className="button primary" onClick={() => void removeAndRetry(outcome.credential)}>
            {words.tryAnother}
          </button>
          <button type="button" className="button" onClick={() => onDone({ credential: outcome.credential, smoke: null })}>
            {words.keepAnyway}
          </button>
        </div>
      </div>
    );
  }

  if (outcome?.kind === "worked") {
    const smoke = outcome.added.smoke;
    return (
      <div className="key-result note note-success" ref={resultRef} tabIndex={-1} role="status">
        <p className="note-title">
          <CircleCheck size={16} aria-hidden="true" /> {words.worked(smoke?.model ?? outcome.added.credential.name)}
        </p>
        {smoke ? <p className="note-hint">{words.workedDetail(tokens(smoke.tokens))}</p> : null}
      </div>
    );
  }

  const busyText = step === "adding" ? words.adding : step === "lineup" ? words.lineup : step === "smoking" ? words.smoking : null;
  return (
    <form className="key-form" onSubmit={(event) => void submit(event)} aria-busy={step !== null}>
      <ErrorNote error={providers.error} />
      <div className="field">
        <label htmlFor={`${id}-provider`}>{words.provider}</label>
        <select
          id={`${id}-provider`}
          value={provider}
          required
          disabled={step !== null || items.length === 0}
          aria-describedby={`${id}-provider-hint`}
          autoFocus={autoFocus}
          onChange={(event) => setProvider(event.target.value)}
        >
          {items.length === 0 ? <option value="">{settingsWords.common.loading}</option> : null}
          {items.map((item) => (
            <option key={item.name} value={item.name}>
              {item.label}
            </option>
          ))}
        </select>
        <p className="quiet" id={`${id}-provider-hint`}>
          {provider === "mock" ? words.mockNote : words.providerHint}
        </p>
      </div>
      <div className="field">
        <label htmlFor={`${id}-key`}>{words.key}</label>
        <input
          id={`${id}-key`}
          type="password"
          autoComplete="off"
          spellCheck={false}
          required
          value={key}
          disabled={step !== null}
          aria-describedby={`${id}-key-hint`}
          onChange={(event) => setKey(event.target.value)}
        />
        <p className="quiet" id={`${id}-key-hint`}>
          {words.keyHint}
        </p>
      </div>
      {chosen?.needs_base_url ? (
        <div className="field">
          <label htmlFor={`${id}-base`}>{words.baseUrl}</label>
          <input
            id={`${id}-base`}
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            required
            placeholder="https://"
            value={baseUrl}
            disabled={step !== null}
            aria-describedby={`${id}-base-hint`}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
          <p className="quiet" id={`${id}-base-hint`}>
            {words.baseUrlHint}
          </p>
        </div>
      ) : null}
      <div className="field">
        <label htmlFor={`${id}-name`}>{words.name}</label>
        <input
          id={`${id}-name`}
          type="text"
          autoComplete="off"
          required
          value={name}
          disabled={step !== null}
          aria-describedby={`${id}-name-hint`}
          onChange={(event) => {
            setNameEdited(true);
            setName(event.target.value);
          }}
        />
        <p className="quiet" id={`${id}-name-hint`}>
          {taken.includes(name.trim()) ? words.nameTaken(name.trim()) : words.nameHint}
        </p>
      </div>
      <ErrorNote error={error} />
      <div className="row wrap key-form-actions">
        <button type="submit" className="button primary" disabled={step !== null || !provider || !key.trim() || !name.trim()}>
          {step !== null ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : null}
          {words.submit}
        </button>
        {onCancel ? (
          <button type="button" className="button ghost" onClick={onCancel} disabled={step !== null}>
            {settingsWords.common.cancel}
          </button>
        ) : null}
        <span className="quiet" role="status" aria-live="polite">
          {busyText ?? ""}
        </span>
      </div>
    </form>
  );
}
