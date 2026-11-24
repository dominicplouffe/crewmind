/**
 * First-run setup in the browser, at `/welcome` (LLM-2, LLM-10, LLM-14, FND-2, ACC-2, FND-1):
 * what nightsquad is, a model key checked with a tiny call, the Founder's key and quality, optional
 * invites, then the goal that starts a drafting conversation. Steps already done are skipped
 * when the person comes back. `?next=/draft/<id>` returns there once the Founder is set up.
 *
 * A member can't change install settings; they are told who can, and how to add a key of their own.
 */
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Check, KeyRound, MessageSquareText, Sparkles } from "lucide-react";
import { get, post } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { AddKeyForm } from "../settings/AddKeyForm";
import { FounderForm } from "../settings/FounderForm";
import { InviteForm, type Invited } from "../settings/InviteForm";
import { safeReturn } from "../settings/paths";
import { useProviderLabels } from "../settings/providers";
import { NameForm } from "../settings/NameForm";
import { settingsWords } from "../strings.settings";
import { LogoMark } from "../ui/Logo";
import { Skeleton } from "../ui/Skeleton";
import { markWelcomeSeen } from "./firstRun";
import { orList, useAdminNames } from "./useAdminNames";
import { founderReadyWith, usableModelKeys } from "./useSetupStatus";

type Step = "welcome" | "key" | "founder" | "invite" | "goal";
const STEPS: Step[] = ["welcome", "key", "founder", "invite", "goal"];
const POINT_ICONS = [KeyRound, Sparkles, MessageSquareText];

function Frame({ children }: { children: ReactNode }): JSX.Element {
  const words = settingsWords.welcome;
  return (
    <div className="welcome">
      <header className="welcome-top">
        <span className="welcome-brand">
          <LogoMark size={28} />
          <span>nightsquad</span>
        </span>
        <Link to="/" className="button ghost">
          {words.exit}
        </Link>
      </header>
      <main className="welcome-main">{children}</main>
    </div>
  );
}

function MemberWelcome(): JSX.Element {
  const words = settingsWords.welcome.member;
  const admins = useAdminNames();
  return (
    <section className="card welcome-card" aria-labelledby="welcome-title">
      <h1 id="welcome-title">{words.title}</h1>
      <p className="welcome-lead">{words.body}</p>
      <div className="note">
        <p className="note-title">{admins.length > 0 ? words.askNamed(orList(admins)) : words.ask}</p>
      </div>
      <p className="quiet">{words.own}</p>
      <div className="welcome-actions">
        <Link to="/" className="button">
          {words.home}
        </Link>
        <span className="spacer" />
        <Link to="/settings/models" className="button primary">
          {words.ownLink}
        </Link>
      </div>
    </section>
  );
}

function GoalForm({ onBack }: { onBack(): void }): JSX.Element {
  const words = settingsWords.welcome.goal;
  const navigate = useNavigate();
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    post("/v1/founder/start", { brief: brief.trim(), document: null })
      .then((view) => navigate(`/draft/${view.drafting_id}`))
      .catch((reason: unknown) => {
        setError(reason);
        setBusy(false);
      });
  };

  return (
    <form onSubmit={submit} className="goal-form">
      <div className="field">
        <label htmlFor="welcome-goal" className="visually-hidden">
          {words.label}
        </label>
        <textarea
          id="welcome-goal"
          className="welcome-goal"
          rows={7}
          required
          value={brief}
          placeholder={words.placeholder}
          aria-describedby="welcome-goal-hint"
          onChange={(event) => setBrief(event.target.value)}
        />
        <p className="quiet" id="welcome-goal-hint">
          {words.hint}
        </p>
      </div>
      <ErrorNote error={error} />
      <div className="welcome-actions">
        <button type="button" className="button ghost" onClick={onBack}>
          {settingsWords.common.back}
        </button>
        <span className="spacer" />
        <Link to="/projects?new=form" className="button ghost">
          {words.byForm}
        </Link>
        <button type="submit" className="button primary large" disabled={busy || !brief.trim()}>
          {busy ? words.busy : words.submit}
        </button>
      </div>
    </form>
  );
}

export function Welcome(): JSX.Element {
  const words = settingsWords.welcome;
  const { person } = useAuth();
  const isAdmin = person?.role === "admin";
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeReturn(params.get("next"));
  const labels = useProviderLabels();
  const status = useLoad(
    () => (isAdmin ? Promise.all([get("/v1/credentials/list"), get("/v1/settings/show_install")]) : Promise.resolve(null)),
    [isAdmin],
  );
  const [step, setStep] = useState<Step | null>(null);
  const [addingAnother, setAddingAnother] = useState(false);
  const [invited, setInvited] = useState<Invited[]>([]);
  const heading = useRef<HTMLHeadingElement>(null);
  const moved = useRef(false);

  const keys = usableModelKeys(status.data?.[0].items ?? []);
  const install = status.data?.[1];
  const setting = (name: string): string => String(install?.items.find((item) => item.name === name)?.value ?? "");
  const credential = setting("founder.credential");
  const founderReady = founderReadyWith(credential, keys);

  useEffect(() => {
    document.title = words.documentTitle;
  }, [words.documentTitle]);

  useEffect(markWelcomeSeen, []);

  // Coming back: skip what is already done.
  useEffect(() => {
    if (step !== null || !status.data) return;
    setStep(keys.length === 0 ? "welcome" : founderReady ? (next ? "founder" : "goal") : "founder");
  }, [status.data, step, keys.length, founderReady, next]);

  // A new step puts focus on its heading (not on first load: the page starts at the top).
  useEffect(() => {
    if (step === null) return;
    if (moved.current) heading.current?.focus();
    moved.current = true;
  }, [step]);

  if (person === undefined || (isAdmin && !status.data && !status.error)) {
    return (
      <Frame>
        <div className="card welcome-card">
          <Skeleton lines={4} block />
        </div>
      </Frame>
    );
  }
  if (!isAdmin) {
    return (
      <Frame>
        <MemberWelcome />
      </Frame>
    );
  }
  if (status.error || step === null) {
    return (
      <Frame>
        <div className="card welcome-card">
          <ErrorNote error={status.error} />
          <button type="button" className="button" onClick={status.reload}>
            {settingsWords.common.retry}
          </button>
        </div>
      </Frame>
    );
  }

  const index = STEPS.indexOf(step);
  const reachable = (target: Step): boolean => {
    if (target === "welcome" || target === "key") return true;
    if (target === "founder") return keys.length > 0;
    return founderReady;
  };
  const go = (target: Step): void => setStep(target);
  const back = (): void => go(STEPS[Math.max(0, index - 1)] ?? "welcome");
  const backButton = (
    <button type="button" className="button ghost" onClick={back}>
      {settingsWords.common.back}
    </button>
  );

  let title: string;
  let lead: string;
  let body: JSX.Element;
  switch (step) {
    case "welcome":
      title = words.intro.title;
      lead = words.intro.lead;
      body = (
        <>
          <p>{words.intro.body}</p>
          <ol className="welcome-points plain">
            {words.intro.points.map((point, position) => {
              const Icon = POINT_ICONS[position] ?? Sparkles;
              return (
                <li key={point.title}>
                  <span className="welcome-point-icon" aria-hidden="true">
                    <Icon size={18} />
                  </span>
                  <span>
                    <strong>{point.title}</strong>
                    <span className="quiet">{point.body}</span>
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="quiet">{words.intro.time}</p>
          <NameForm compact />
          <div className="welcome-actions">
            <span className="spacer" />
            <button type="button" className="button primary large" onClick={() => go(keys.length > 0 && founderReady ? "goal" : keys.length > 0 ? "founder" : "key")}>
              {words.intro.start}
            </button>
          </div>
        </>
      );
      break;
    case "key":
      title = words.key.title;
      lead = words.key.lead;
      body = (
        <>
          {keys.length > 0 ? (
            <div className="note note-success">
              <p className="note-title">{words.key.have}</p>
              <ul className="welcome-keys plain" aria-label={words.key.haveList}>
                {keys.map((key) => (
                  <li key={key.name}>
                    <Check size={14} aria-hidden="true" /> {key.name} <span className="quiet">· {labels(key.provider)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {keys.length === 0 || addingAnother ? (
            <AddKeyForm
              existingNames={keys.map((key) => key.name)}
              autoFocus
              onDone={() => {
                setAddingAnother(false);
                status.reload();
              }}
            />
          ) : (
            <button type="button" className="button" onClick={() => setAddingAnother(true)}>
              {words.key.addAnother}
            </button>
          )}
          <details className="welcome-help">
            <summary>{words.key.where}</summary>
            <p className="quiet">{words.key.whereBody}</p>
          </details>
          <div className="welcome-actions">
            {backButton}
            <span className="spacer" />
            <button type="button" className="button primary large" disabled={keys.length === 0} onClick={() => go("founder")}>
              {settingsWords.common.continue}
            </button>
          </div>
        </>
      );
      break;
    case "founder":
      title = words.founder.title;
      lead = words.founder.lead;
      body = (
        <FounderForm
          key={`${credential}-${setting("founder.model_class")}`}
          keys={keys}
          credential={credential}
          modelClass={setting("founder.model_class")}
          reason={words.founder.reason}
          submitLabel={settingsWords.common.continue}
          before={
            <>
              {backButton}
              <span className="spacer" />
            </>
          }
          onSaved={(view) => {
            if (view && status.data) status.setData([status.data[0], view]);
            if (next) navigate(next);
            else go("invite");
          }}
        />
      );
      break;
    case "invite":
      title = words.invite.title;
      lead = words.invite.lead;
      body = (
        <>
          {invited.length > 0 ? (
            <ul className="welcome-invited plain" aria-label={words.invite.invited}>
              {invited.map((person) => (
                <li key={person.link.person_id}>
                  <Check size={14} aria-hidden="true" /> {person.name} <span className="quiet">· {person.email}</span>
                </li>
              ))}
            </ul>
          ) : null}
          <InviteForm onInvited={(person) => setInvited((current) => [...current, person])} />
          <div className="welcome-actions">
            {backButton}
            <span className="spacer" />
            <button type="button" className={invited.length > 0 ? "button primary large" : "button ghost large"} onClick={() => go("goal")}>
              {invited.length > 0 ? settingsWords.common.continue : words.invite.skip}
            </button>
          </div>
        </>
      );
      break;
    default:
      title = words.goal.title;
      lead = words.goal.lead;
      body = <GoalForm onBack={back} />;
  }

  return (
    <Frame>
      <nav className="welcome-steps" aria-label={words.steps}>
        <ol className="plain">
          {STEPS.map((target, position) => {
            const done = position < index;
            const state = target === step ? "current" : done ? "done" : "todo";
            return (
              <li key={target} className={`welcome-step ${state}`}>
                <button
                  type="button"
                  aria-current={target === step ? "step" : undefined}
                  disabled={!reachable(target) || target === step}
                  onClick={() => go(target)}
                >
                  <span className="welcome-step-dot" aria-hidden="true">
                    {done ? <Check size={12} strokeWidth={3} /> : position + 1}
                  </span>
                  <span className="welcome-step-name">{words.stepNames[target]}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
      <section className="card welcome-card" key={step} aria-labelledby="welcome-title">
        <p className="eyebrow">{words.stepOf(index + 1, STEPS.length)}</p>
        <h1 id="welcome-title" tabIndex={-1} ref={heading}>
          {title}
        </h1>
        <p className="welcome-lead">{lead}</p>
        {body}
      </section>
    </Frame>
  );
}
