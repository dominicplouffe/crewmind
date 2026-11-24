/**
 * What stands between this draft and a project, as a checklist in the order the work happens
 * (FND-5, FND-6, FND-11): a draft, the questions answered, every decision made, the goal graded
 * ready, a rehearsal to its first close. Each open check says the server's own reason. The server's
 * `ready` is the only verdict; this lays it out so what is left is never a guess.
 */
import { Check as CheckIcon, Circle, CircleDot } from "lucide-react";
import { t } from "../strings";
import { founder as words } from "../strings.founder";
import { GoalGrade } from "./GoalGrade";
import { readinessChecks, readinessReasons, settledCount, type Check, type Drafting, type Grade, type Stage } from "./logic";

interface Props {
  view: Drafting;
  stage: Stage;
  grade: Grade | null;
}

const ICONS = { done: CheckIcon, todo: CircleDot, later: Circle };

/** One segment per decision, in order: settled, being asked, or open. */
function DecisionBar({ view }: { view: Drafting }): JSX.Element {
  return (
    <span className="decision-bar" aria-hidden="true">
      {view.decisions.map((decision) => (
        <span key={decision.key} className={`decision-bar-part part-${decision.state}`} />
      ))}
    </span>
  );
}

function Detail({ check, view, grade }: { check: Check; view: Drafting; grade: Grade | null }): JSX.Element {
  const said = words.checks;
  if (check.key === "decisions" && check.status !== "later") {
    return (
      <>
        <p className="check-detail">{said.decisionsCount(settledCount(view.decisions), view.decisions.length)}</p>
        <DecisionBar view={view} />
      </>
    );
  }
  if (check.key === "goal" && grade) {
    return (
      <>
        <p className="check-detail" data-testid="grade-summary">
          {grade.summary}
        </p>
        <details className="fold">
          <summary>{said.gradeShow}</summary>
          <GoalGrade grade={grade} />
        </details>
      </>
    );
  }
  if (check.key === "rehearsal") {
    // The verdict kept may be of an earlier draft: while this one is not rehearsed, the server's reason says so.
    const shown =
      check.status === "later" ? said.later : (check.reason ?? view.rehearsal ?? t.founder.side.rehearsalNone);
    return (
      <p className="check-detail" data-testid="draft-rehearsal">
        {shown}
      </p>
    );
  }
  if (check.status === "later") return <p className="check-detail">{said.later}</p>;
  if (check.status === "done") return <p className="check-detail">{said.done[check.key] ?? ""}</p>;
  const reason = check.reason ? readinessReasons([check.reason])[0] : undefined;
  return <p className="check-detail">{reason?.text ?? ""}</p>;
}

export function ReadyChecklist({ view, stage, grade }: Props): JSX.Element {
  const said = words.checks;
  const checks = readinessChecks(view);
  const done = checks.filter((check) => check.status === "done").length;
  return (
    <section className="rail-card checks" aria-labelledby="checks-title" data-testid="readiness" data-stage={stage}>
      <header className="rail-head">
        <h2 id="checks-title">{said.title}</h2>
        <span className="rail-count">{said.progress(done, checks.length)}</span>
      </header>
      <ol className="check-list">
        {checks.map((check) => {
          const Icon = ICONS[check.status];
          return (
            <li key={check.key} className={`check check-${check.status}`} data-testid="check" data-check={check.key} data-status={check.status}>
              <span className="check-mark">
                <Icon size={14} aria-hidden="true" strokeWidth={check.status === "done" ? 3 : 2} />
              </span>
              <div className="check-body">
                <p className="check-name">
                  {said.names[check.key] ?? check.key}
                  <span className="visually-hidden"> ({said.status[check.status]})</span>
                </p>
                <Detail check={check} view={view} grade={grade} />
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
