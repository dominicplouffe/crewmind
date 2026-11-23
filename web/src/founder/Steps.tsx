/** The four steps of drafting a project, with the one the person is on (FND-1). Display only. */
import { t } from "../strings";
import { STEPS, type StepName } from "./logic";

export function Steps({ current }: { current: StepName }): JSX.Element {
  const words = t.founder.steps;
  const at = STEPS.indexOf(current);
  return (
    <ol className="draft-steps" aria-label={words.label} data-testid="draft-steps" data-step={current}>
      {STEPS.map((step, index) => {
        const status = index < at ? "done" : index === at ? "now" : "todo";
        return (
          <li key={step} className={`draft-step step-${status}`} aria-current={status === "now" ? "step" : undefined}>
            <span className="step-number" aria-hidden="true">
              {index + 1}
            </span>
            <span>{words.names[step]}</span>
            <span className="visually-hidden"> ({words.status[status]})</span>
          </li>
        );
      })}
    </ol>
  );
}
