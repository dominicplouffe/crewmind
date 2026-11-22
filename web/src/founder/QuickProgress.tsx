/** Where quick mode stands (FND-12): drafting, creating, starting, started; or failed with nothing created. */
import { t } from "../strings";
import { quickSteps } from "./logic";

export function QuickProgress({ state }: { state: string }): JSX.Element {
  const words = t.founder.quick;
  return (
    <section className="note" aria-labelledby="quick-title" data-testid="quick-progress">
      <h2 id="quick-title">{words.title}</h2>
      <p>{state === "failed" ? words.failed : words.intro}</p>
      <div role="status">
        <ol className="quick-steps" aria-label={words.stepsLabel}>
        {quickSteps(state).map(({ step, status }) => (
            <li key={step} className={`step-${status}`} aria-current={status === "now" ? "step" : undefined} data-status={status}>
              {words.step(words.steps[step] ?? step, words.status[status] ?? status)}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
