/**
 * Model keys (LLM-2, LLM-10): each with its provider, state and the models found, a Test button
 * that makes one tiny call, delete with a confirmation, and a form to add one. Members see and
 * manage their own keys; an admin sees every key on the install.
 */
import { useState } from "react";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { get, post, type Schemas } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { tokens } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { refreshSetupStatus } from "../onboarding/useSetupStatus";
import { settingsWords } from "../strings.settings";
import { Skeleton } from "../ui/Skeleton";
import { Pill } from "../ui/Status";
import { AddKeyForm, failureKind, type AddedKey } from "./AddKeyForm";
import { useProviderLabels } from "./providers";

type Credential = Schemas["CredentialItem"];
type Smoke = Schemas["SmokeResult"];

function KeyRow({
  credential,
  providerLabel,
  founder,
  mine,
  onChanged,
}: {
  credential: Credential;
  providerLabel: string;
  founder: boolean;
  mine: boolean;
  onChanged(): void;
}): JSX.Element {
  const words = settingsWords.models;
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<Smoke | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const models = Object.keys(credential.lineup).length;
  const isModel = credential.kind === "model";

  const test = (): void => {
    setTesting(true);
    setError(null);
    setResult(null);
    post("/v1/credentials/smoke", { name: credential.name })
      .then(setResult)
      .catch((reason: unknown) => setError(reason))
      .finally(() => setTesting(false));
  };

  const remove = (): void => {
    setBusy(true);
    setError(null);
    post("/v1/credentials/delete", { name: credential.name })
      .then(() => {
        refreshSetupStatus();
        onChanged();
      })
      .catch((reason: unknown) => {
        setError(reason);
        setBusy(false);
      });
  };

  const meta = [providerLabel, isModel ? words.models(models) : words.searchKey].join(" · ");
  return (
    <li className="key-row" data-testid="credential">
      <div className="key-row-main">
        <span className="key-icon" aria-hidden="true">
          <KeyRound size={18} />
        </span>
        <div className="key-text">
          <p className="key-name">
            <span>{credential.name}</span>
            {credential.state !== "active" ? <Pill tone="neutral">{words.state[credential.state] ?? credential.state}</Pill> : null}
            {credential.breaker === "open" ? <Pill tone="danger">{words.breakerOpen}</Pill> : null}
            {credential.breaker === "half_open" ? <Pill tone="warning">{words.breakerHalf}</Pill> : null}
            {founder ? <Pill tone="accent" dot={false}>{words.founderBadge}</Pill> : null}
          </p>
          <p className="quiet">
            {meta}
            {mine ? "" : ` · ${words.owner}`}
          </p>
        </div>
        <div className="key-actions">
          {isModel ? (
            <button type="button" className="button small" onClick={test} disabled={testing || busy}>
              {testing ? words.testing : words.test}
              <span className="visually-hidden"> {credential.name}</span>
            </button>
          ) : null}
          <button
            type="button"
            className="button small ghost icon-only"
            aria-label={`${words.delete} ${credential.name}`}
            aria-expanded={confirming}
            onClick={() => setConfirming(true)}
            disabled={busy}
          >
            <Trash2 size={16} aria-hidden="true" />
          </button>
        </div>
      </div>
      {result ? (
        result.ok ? (
          <p className="note note-success key-test" role="status">
            {settingsWords.keyForm.worked(result.model)} {settingsWords.keyForm.workedDetail(tokens(result.tokens))}
          </p>
        ) : (
          <div className="note note-error key-test" role="alert">
            <p className="note-title">{words.testFailed}</p>
            <p className="note-hint">{settingsWords.keyForm.failedFix[failureKind(result.detail)]}</p>
            <details className="key-detail-toggle">
              <summary>{settingsWords.keyForm.details}</summary>
              <pre className="key-detail">{result.detail}</pre>
            </details>
          </div>
        )
      ) : null}
      <ErrorNote error={error} />
      {confirming ? (
        <div className="note note-warning key-confirm" role="group" aria-label={words.deleteYes}>
          <p className="note-title">{words.deleteConfirm(credential.name)}</p>
          <div className="note-actions">
            <button type="button" className="button danger" onClick={remove} disabled={busy}>
              {words.deleteYes}
            </button>
            <button type="button" className="button" onClick={() => setConfirming(false)} disabled={busy} autoFocus>
              {words.keep}
            </button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function ModelsSection(): JSX.Element {
  const words = settingsWords.models;
  const { person } = useAuth();
  const isAdmin = person?.role === "admin";
  const list = useLoad(() => get("/v1/credentials/list"), []);
  const install = useLoad(() => (isAdmin ? get("/v1/settings/show_install") : Promise.resolve(null)), [isAdmin]);
  const labels = useProviderLabels();
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState<AddedKey | null>(null);
  const items = list.data?.items ?? [];
  const founderKey = install.data?.items.find((item) => item.name === "founder.credential")?.value;
  const showForm = adding || (list.data !== undefined && items.length === 0);

  return (
    <>
      <section className="card settings-card" aria-labelledby="keys-title">
        <div className="settings-card-head with-action">
          <div>
            <h3 id="keys-title">{isAdmin ? words.listTitleAdmin : words.listTitle}</h3>
            <p className="quiet">{isAdmin ? words.intro : `${words.intro} ${words.memberIntro}`}</p>
          </div>
          {items.length > 0 && !adding ? (
            <button
              type="button"
              className="button primary"
              onClick={() => {
                setAdded(null);
                setAdding(true);
              }}
            >
              <Plus size={16} aria-hidden="true" />
              {words.add}
            </button>
          ) : null}
        </div>
        {list.error ? (
          <div className="stack">
            <ErrorNote error={list.error} />
            <div>
              <button type="button" className="button small" onClick={list.reload}>
                {settingsWords.common.retry}
              </button>
            </div>
          </div>
        ) : null}
        {added ? (
          <div className="note note-success key-added" role="status">
            <p className="note-title">
              {added.smoke ? settingsWords.keyForm.worked(added.smoke.model) : words.addedUntested(added.credential.name)}
            </p>
            <div className="note-actions">
              <button type="button" className="button small" onClick={() => setAdded(null)}>
                {settingsWords.common.close}
              </button>
            </div>
          </div>
        ) : null}
        {list.loading && !list.data ? <Skeleton lines={3} block /> : null}
        {list.data && items.length === 0 && !adding ? (
          <div className="empty compact">
            <span className="empty-icon" aria-hidden="true">
              <KeyRound size={20} />
            </span>
            <p className="empty-title">{words.emptyTitle}</p>
            <p className="quiet">{words.emptyBody}</p>
          </div>
        ) : null}
        {items.length > 0 ? (
          <ul className="key-list plain" aria-label={words.title}>
            {items.map((credential) => (
              <KeyRow
                key={credential.name}
                credential={credential}
                providerLabel={labels(credential.provider)}
                founder={founderKey === credential.name}
                mine={credential.owner_id === person?.person_id}
                onChanged={list.reload}
              />
            ))}
          </ul>
        ) : null}
      </section>
      {showForm && list.data ? (
        <section className="card settings-card" aria-labelledby="add-key-title">
          <div className="settings-card-head">
            <h3 id="add-key-title">{settingsWords.keyForm.title}</h3>
          </div>
          <AddKeyForm
            existingNames={items.map((item) => item.name)}
            autoFocus={adding}
            onCancel={items.length > 0 ? () => setAdding(false) : undefined}
            onDone={(result) => {
              setAdded(result);
              setAdding(false);
              list.reload();
              install.reload();
            }}
          />
        </section>
      ) : null}
    </>
  );
}
