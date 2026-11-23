/**
 * Whether the draft can become a project (FND-5, FND-13): what still stands in the way, the button
 * that creates it, and after creation what is still needed and the offer to start.
 */
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { t } from "../strings";
import { readinessReasons, type Drafting, type Stage } from "./logic";
import type { CreatedProject } from "./useDrafting";

interface Props {
  view: Drafting;
  stage: Stage;
  /** What `founder create` answered, when the project was created on this page. */
  created: CreatedProject | null;
  busy: boolean;
  onCreate(): void;
  onStart(): void;
}

function Created({ view, created, busy, onStart }: Pick<Props, "view" | "created" | "busy" | "onStart">): JSX.Element {
  const words = t.founder.ready;
  const heading = useRef<HTMLHeadingElement>(null);
  const projectId = created?.project_id ?? view.project_id ?? "";
  // The create button is gone: put focus on what replaced it.
  useEffect(() => {
    if (created) heading.current?.focus();
  }, [created]);

  return (
    <section className="note" aria-labelledby="created-title" data-testid="created">
      <h2 id="created-title" tabIndex={-1} ref={heading}>
        {view.state === "started" ? words.started : created ? words.created(created.name) : words.createdPlain}
      </h2>
      {created ? (
        <>
          <h3 className="group-title">{words.missingTitle}</h3>
          {created.missing.length === 0 ? (
            <p data-testid="nothing-missing">{words.nothingMissing}</p>
          ) : (
            <ul className="checklist" data-testid="still-missing">
              {created.missing.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
          {created.waiting.length > 0 ? (
            <>
              <h3 className="group-title">{words.waitingTitle}</h3>
              <ul className="checklist" data-testid="crew-waiting">
                {created.waiting.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <p className="quiet">{words.waitingAfter}</p>
              {projectId ? (
                <p>
                  <Link to={`/projects/${projectId}?panel=connections`} data-testid="add-missing">
                    {words.addMissing}
                  </Link>
                </p>
              ) : null}
            </>
          ) : null}
        </>
      ) : null}
      <div className="row wrap">
        {created?.can_start ? (
          <button type="button" className="button primary" disabled={busy} onClick={onStart}>
            {busy ? words.starting : created.waiting.length > 0 ? words.startWithout : words.start}
          </button>
        ) : null}
        {projectId ? (
          <Link to={`/projects/${projectId}`} className="button">
            {created?.can_start ? words.later : words.open}
          </Link>
        ) : null}
      </div>
    </section>
  );
}

export function Readiness({ view, stage, created, busy, onCreate, onStart }: Props): JSX.Element | null {
  const words = t.founder.ready;
  if (stage === "done") return <Created view={view} created={created} busy={busy} onStart={onStart} />;
  if (stage === "failed") {
    return (
      <section className="note note-error" aria-labelledby="readiness-title" data-testid="readiness" data-stage={stage}>
        <h2 id="readiness-title" className="note-title">
          {words.failed}
        </h2>
        {view.failure ? <p>{view.failure}</p> : null}
        <Link to="/draft">{words.failedNext}</Link>
      </section>
    );
  }
  // In quick mode nothing waits on the person: the progress list says where it stands.
  if (stage === "quick") return null;
  if (stage === "ready") {
    return (
      <section className="note" aria-labelledby="readiness-title" data-testid="readiness" data-stage={stage}>
        <h2 id="readiness-title">{words.ready}</h2>
        <p>{words.readyIntro}</p>
        <button type="button" className="button primary" disabled={busy} onClick={onCreate}>
          {busy ? words.creating : words.create}
        </button>
      </section>
    );
  }
  const reasons = readinessReasons(view.not_ready_because);
  return (
    <section className="note" aria-labelledby="readiness-title" data-testid="readiness" data-stage={stage}>
      <h2 id="readiness-title">{words.notReady}</h2>
      <p className="quiet">{words.notReadyIntro}</p>
      <ul data-testid="not-ready-because">
        {reasons.map((reason) => (
          <li key={reason.text}>
            {reason.text}
            {reason.parts.length > 0 ? (
              <ul>
                {reason.parts.map((part) => (
                  <li key={part}>{part}</li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
