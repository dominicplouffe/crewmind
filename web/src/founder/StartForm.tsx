/**
 * The way into drafting: one box for what the person wants, an optional text document to grill
 * first (FND-15), and quick mode as the secondary choice (FND-12). Quick mode never picks who
 * pays: when the server asks, the person chooses a credential and the request is sent again.
 */
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, get, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatNumber } from "../lib/format";
import { t } from "../strings";
import { credentialsInHint, documentProblem } from "./logic";

interface Attached {
  name: string;
  text: string;
}

export function StartForm(): JSX.Element {
  const words = t.founder.start;
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [brief, setBrief] = useState("");
  const [attached, setAttached] = useState<Attached | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"talk" | "quick" | null>(null);
  /** The credentials to choose from, once the server said quick mode needs to know who pays. */
  const [payers, setPayers] = useState<string[] | null>(null);
  const [payer, setPayer] = useState("");

  // The server asked who pays: put focus on the choice it needs.
  const payerChoice = useRef<HTMLFieldSetElement>(null);
  useEffect(() => {
    if (payers) payerChoice.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, [payers]);

  const onFile = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0];
    setAttached(null);
    setFileError(null);
    if (!file) return;
    try {
      const text = await file.text();
      const problem = documentProblem(file.name, text);
      if (problem) setFileError(problem);
      else setAttached({ name: file.name, text });
    } catch {
      setFileError(words.unreadable);
    }
    if (fileInput.current) fileInput.current.value = "";
  };

  const open = (draftingId: string): void => navigate(`/draft/${draftingId}`);

  const startTalking = async (): Promise<void> => {
    const view = await post("/v1/founder/start", { brief: brief.trim(), document: attached?.text ?? null });
    open(view.drafting_id);
  };

  const startQuick = async (): Promise<void> => {
    try {
      const view = await post("/v1/founder/quick", { brief: brief.trim(), credential: payer || null });
      open(view.drafting_id);
    } catch (reason) {
      if (!(reason instanceof ApiError) || reason.refusal?.code !== "say_who_pays") throw reason;
      let names = credentialsInHint(reason.hint);
      if (names.length === 0) {
        const mine = await get("/v1/credentials/list");
        names = mine.items.filter((item) => item.kind === "model").map((item) => item.name);
      }
      setPayers(names);
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter;
    const mode = submitter instanceof HTMLElement && submitter.dataset.mode === "quick" ? "quick" : "talk";
    setBusy(mode);
    setError(null);
    (mode === "quick" ? startQuick() : startTalking())
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(null));
  };

  return (
    <form className="start-form" onSubmit={submit} aria-labelledby="start-title">
      <p className="lead">{words.intro}</p>
      <div className="field">
        <label htmlFor="brief">{words.brief}</label>
        <textarea
          id="brief"
          className="brief"
          required
          autoFocus
          rows={8}
          value={brief}
          aria-describedby="brief-hint"
          onChange={(event) => setBrief(event.target.value)}
        />
        <p className="quiet" id="brief-hint">
          {words.briefHint}
        </p>
      </div>
      <div className="field">
        <label htmlFor="brief-document">{words.attach}</label>
        <input
          id="brief-document"
          type="file"
          accept=".txt,.md,.markdown,text/plain,text/markdown"
          ref={fileInput}
          aria-describedby="brief-document-hint"
          onChange={(event) => void onFile(event)}
        />
        <p className="quiet" id="brief-document-hint">
          {words.attachHint}
        </p>
        {attached ? (
          <p className="row wrap" role="status" data-testid="attached">
            <span>{words.attached(attached.name, formatNumber(attached.text.length))}</span>
            <button type="button" className="link" onClick={() => setAttached(null)}>
              {words.remove}
            </button>
          </p>
        ) : null}
        {fileError ? (
          <p className="note note-error" role="alert">
            {fileError}
          </p>
        ) : null}
      </div>
      <ErrorNote error={error} />
      <button type="submit" className="button primary" disabled={busy !== null}>
        {busy === "talk" ? words.busy : words.submit}
      </button>
      <section className="quick-choice" aria-labelledby="quick-choice-title">
        <h2 id="quick-choice-title">{words.quickTitle}</h2>
        <p className="quiet">{words.quickIntro}</p>
        {attached ? <p className="quiet">{words.quickNoDocument}</p> : null}
        {payers ? (
          <fieldset className="plan-fieldset" data-testid="who-pays" ref={payerChoice}>
            <legend>{words.payTitle}</legend>
            <p className="quiet">{words.payIntro}</p>
            {payers.map((name) => (
              <div key={name} className="check-field payer">
                <input
                  type="radio"
                  id={`payer-${name}`}
                  name="payer"
                  value={name}
                  checked={payer === name}
                  onChange={() => setPayer(name)}
                />
                <label htmlFor={`payer-${name}`}>{name}</label>
              </div>
            ))}
          </fieldset>
        ) : null}
        <button type="submit" className="button" data-mode="quick" disabled={busy !== null || (payers !== null && payer === "")}>
          {busy === "quick" ? words.quickBusy : payers ? words.payGo : words.quickSubmit}
        </button>
      </section>
    </form>
  );
}
