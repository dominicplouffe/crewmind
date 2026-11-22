/** The form that adds a requirement to the plan. */
import { useId, useState, type FormEvent } from "react";
import { post } from "../../api/client";
import { ErrorNote, Field } from "../../components/common";
import { t } from "../../strings";
import { wholeNumber } from "./logic";
import type { PlanTabProps, Requirement } from "./parts";

const KINDS = ["observable", "command", "metric"] as const;
type Kind = (typeof KINDS)[number];
/** A new requirement starts in the first stage unless the chairman says otherwise. */
const FIRST_STAGE = "1";

interface Props extends Pick<PlanTabProps, "projectId" | "apply" | "type"> {
  /** Open requirements this one could wait on. */
  others: Requirement[];
  onDone(): void;
}

export function AddRequirement({ projectId, apply, type, others, onDone }: Props): JSX.Element {
  const words = t.plan.scope.add;
  const id = useId();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<Kind>("observable");
  const [successTest, setSuccessTest] = useState("");
  const [estimate, setEstimate] = useState("");
  const [stage, setStage] = useState(FIRST_STAGE);
  const [dependsOn, setDependsOn] = useState<number[]>([]);
  const [recurring, setRecurring] = useState(false);
  const [metricUrl, setMetricUrl] = useState("");
  const [metricPattern, setMetricPattern] = useState("");
  const [metricTarget, setMetricTarget] = useState("");
  const [metricAtLeast, setMetricAtLeast] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const send = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apply(() =>
        post("/v1/requirements/add", {
          project_id: projectId,
          text,
          test_kind: kind,
          success_test: kind === "metric" ? undefined : successTest,
          estimate_runs: wholeNumber(estimate) ?? undefined,
          stage: wholeNumber(stage) ?? undefined,
          depends_on: dependsOn.length > 0 ? dependsOn : undefined,
          recurring: type === "operate" ? recurring : undefined,
          ...(kind === "metric"
            ? {
                metric_url: metricUrl,
                metric_pattern: metricPattern,
                metric_target: metricTarget.trim() === "" ? undefined : Number(metricTarget),
                metric_at_least: metricAtLeast,
              }
            : {}),
        }),
      );
      onDone();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="plan-form" aria-labelledby={`${id}-title`} onSubmit={(event) => void send(event)} data-testid="add-requirement">
      <h3 className="group-title" id={`${id}-title`}>
        {words.title}
      </h3>
      <Field label={words.text} htmlFor={`${id}-text`} hint={words.textHint}>
        <textarea id={`${id}-text`} rows={3} required autoFocus aria-describedby={`${id}-text-hint`} value={text} onChange={(event) => setText(event.target.value)} />
      </Field>
      <Field label={words.kind} htmlFor={`${id}-kind`}>
        <select id={`${id}-kind`} value={kind} onChange={(event) => setKind(event.target.value as Kind)}>
          {KINDS.map((value) => (
            <option key={value} value={value}>
              {t.plan.scope.testKinds[value]}
            </option>
          ))}
        </select>
      </Field>
      {kind === "metric" ? (
        <>
          <Field label={words.metricUrl} htmlFor={`${id}-url`}>
            <input id={`${id}-url`} type="url" required value={metricUrl} onChange={(event) => setMetricUrl(event.target.value)} />
          </Field>
          <Field label={words.metricPattern} htmlFor={`${id}-pattern`} hint={words.metricPatternHint}>
            <input id={`${id}-pattern`} required aria-describedby={`${id}-pattern-hint`} value={metricPattern} onChange={(event) => setMetricPattern(event.target.value)} />
          </Field>
          <Field label={words.metricTarget} htmlFor={`${id}-target`}>
            <input id={`${id}-target`} type="number" step="any" required value={metricTarget} onChange={(event) => setMetricTarget(event.target.value)} />
          </Field>
          <p className="check-field">
            <input id={`${id}-at-least`} type="checkbox" checked={metricAtLeast} onChange={(event) => setMetricAtLeast(event.target.checked)} />
            <label htmlFor={`${id}-at-least`}>{words.metricAtLeast}</label>
          </p>
        </>
      ) : (
        <Field label={words.successTest[kind] ?? words.kind} htmlFor={`${id}-test`}>
          <textarea id={`${id}-test`} rows={2} required value={successTest} onChange={(event) => setSuccessTest(event.target.value)} />
        </Field>
      )}
      <Field label={words.estimate} htmlFor={`${id}-estimate`}>
        <input id={`${id}-estimate`} type="number" min={1} value={estimate} onChange={(event) => setEstimate(event.target.value)} />
      </Field>
      <Field label={words.stage} htmlFor={`${id}-stage`} hint={words.stageHint}>
        <input id={`${id}-stage`} type="number" min={1} required aria-describedby={`${id}-stage-hint`} value={stage} onChange={(event) => setStage(event.target.value)} />
      </Field>
      {others.length > 0 ? (
        <fieldset className="plan-fieldset">
          <legend>{words.dependsOn}</legend>
          {others.map((other) => (
            <p key={other.id} className="check-field">
              <input
                id={`${id}-after-${other.id}`}
                type="checkbox"
                checked={dependsOn.includes(other.id)}
                onChange={(event) =>
                  setDependsOn((old) => (event.target.checked ? [...old, other.id] : old.filter((value) => value !== other.id)))
                }
              />
              <label htmlFor={`${id}-after-${other.id}`}>
                {t.plan.scope.name(other.id)}: {other.text}
              </label>
            </p>
          ))}
        </fieldset>
      ) : null}
      {type === "operate" ? (
        <p className="check-field">
          <input id={`${id}-recurring`} type="checkbox" checked={recurring} onChange={(event) => setRecurring(event.target.checked)} />
          <label htmlFor={`${id}-recurring`}>{words.recurring}</label>
        </p>
      ) : null}
      <ErrorNote error={error} />
      <div className="row wrap">
        <button type="submit" className="button small primary" disabled={busy}>
          {words.submit}
        </button>
        <button type="button" className="button small" onClick={onDone}>
          {t.common.cancel}
        </button>
      </div>
    </form>
  );
}
