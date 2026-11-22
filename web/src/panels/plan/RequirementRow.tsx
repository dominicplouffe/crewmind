/** One requirement: its state, estimate, what it waits on, its test and reading, and what the chairman can do to it. */
import { useState } from "react";
import { ApiError, post } from "../../api/client";
import { formatDateTime, formatNumber } from "../../lib/format";
import { t } from "../../strings";
import { webAddress } from "../board/logic";
import { AgentText } from "../board/parts";
import { isSettled, requirementActions, wholeNumber } from "./logic";
import { ActionButton, FieldsForm, StateTag, type PlanTabProps, type Requirement } from "./parts";

type Mode = "decline" | "cut" | "estimate" | "reject" | null;

interface Props extends Pick<PlanTabProps, "projectId" | "busy" | "run" | "apply" | "refusal"> {
  requirement: Requirement;
  /** Above 1 when estimates are being adjusted upwards. */
  multiplier: number;
}

function Metric({ metric }: { metric: NonNullable<Requirement["metric"]> }): JSX.Element {
  const words = t.plan.scope.metric;
  const address = webAddress(metric.url);
  return (
    <div data-testid="requirement-metric">
      <p className="quiet">
        {words.target(formatNumber(metric.target), metric.at_least)} ·{" "}
        {metric.latest === null || metric.latest === undefined
          ? words.noReading
          : words.latest(formatNumber(metric.latest), metric.read_at ? formatDateTime(metric.read_at) : t.plan.unknown)}
      </p>
      {metric.failure ? <p>{words.failure(metric.failure)}</p> : null}
      {metric.losing_ground ? <p>{words.losingGround}</p> : null}
      <p className="quiet">
        {words.page}:{" "}
        {address ? (
          <a href={address} target="_blank" rel="noreferrer noopener">
            {metric.url} <span className="visually-hidden">{t.board.evidence.newTab}</span>
          </a>
        ) : (
          metric.url
        )}
      </p>
    </div>
  );
}

export function RequirementRow({ projectId, busy, run, apply, requirement, multiplier, refusal }: Props): JSX.Element {
  const [mode, setMode] = useState<Mode>(null);
  const [acceptTried, setAcceptTried] = useState(false);
  const words = t.plan.scope;
  const ref = { project_id: projectId, requirement_id: requirement.id };
  const of = words.of(requirement.id);
  const actions = requirementActions(requirement);
  const doesNotFit =
    acceptTried && refusal instanceof ApiError && refusal.refusal?.code === "does_not_fit_budget" && actions.includes("accept");

  const accept = (anyway: boolean): void => {
    setAcceptTried(true);
    void run(() => post("/v1/requirements/accept", anyway ? { ...ref, anyway: true } : ref));
  };
  const reasonForm = (label: string, submit: string, path: "/v1/requirements/decline" | "/v1/requirements/cut"): JSX.Element => (
    <FieldsForm
      fields={[{ name: "reason", label, multiline: true, required: true }]}
      submit={submit}
      onCancel={() => setMode(null)}
      onSubmit={async ({ reason }) => {
        await apply(() => post(path, { ...ref, reason: reason ?? "" }));
        setMode(null);
      }}
    />
  );

  return (
    <li data-testid="requirement" data-requirement-id={requirement.id} className={isSettled(requirement.state) ? "is-past" : ""}>
      <p className="record-text">
        <span className="quiet">{words.name(requirement.id)}</span> <AgentText text={requirement.text} />
      </p>
      <p className="quiet row wrap">
        <StateTag state={requirement.state} />
        <span>{words.author[requirement.author] ?? words.authorOther(requirement.author)}</span>
        {requirement.recurring ? <span className="marker">{words.recurring}</span> : null}
      </p>
      <p className="quiet" data-testid="requirement-estimate">
        {requirement.estimate_runs == null ? words.noEstimate : words.estimate(requirement.estimate_runs)}
        {multiplier > 1 && requirement.adjusted_runs != null ? ` (${words.adjusted(requirement.adjusted_runs)})` : ""}
        {requirement.actual_runs ? ` · ${words.actual(requirement.actual_runs)}` : ""}
        {requirement.failures > 0 ? ` · ${words.failures(requirement.failures)}` : ""}
      </p>
      {requirement.depends_on.length > 0 ? (
        <p className="quiet" data-testid="requirement-depends">
          {words.dependsOn(requirement.depends_on.map((id) => words.of(id)).join(", "))}
        </p>
      ) : null}
      {isSettled(requirement.state) ? null : (
        <p data-testid="requirement-ready">
          {requirement.ready ? words.ready : words.notReady(requirement.not_ready_because ?? t.plan.unknown)}
        </p>
      )}
      <p className="quiet">
        {words.test}: {words.testKinds[requirement.test_kind] ?? requirement.test_kind}
      </p>
      {requirement.success_test ? (
        <p>
          <AgentText text={requirement.success_test} />
        </p>
      ) : requirement.metric ? null : (
        <p className="quiet">{words.noTest}</p>
      )}
      {requirement.metric ? <Metric metric={requirement.metric} /> : null}
      {requirement.ruling ? (
        <p>
          {words.ruling(requirement.ruling)}
          {requirement.ruling_note ? (
            <>
              {": "}
              <AgentText text={requirement.ruling_note} />
            </>
          ) : null}
        </p>
      ) : null}
      {requirement.reason ? <p>{words.reason(requirement.reason)}</p> : null}

      {mode === "decline" ? reasonForm(words.declineReason, words.declineSubmit, "/v1/requirements/decline") : null}
      {mode === "cut" ? reasonForm(words.cutReason, words.cutSubmit, "/v1/requirements/cut") : null}
      {mode === "estimate" ? (
        <FieldsForm
          fields={[
            { name: "runs", label: words.estimateLabel, type: "number", required: true, initial: String(requirement.estimate_runs ?? "") },
          ]}
          submit={words.estimateSubmit}
          onCancel={() => setMode(null)}
          onSubmit={async ({ runs }) => {
            await apply(() => post("/v1/requirements/change", { ...ref, estimate_runs: wholeNumber(runs ?? "") }));
            setMode(null);
          }}
        />
      ) : null}
      {mode === "reject" ? (
        <FieldsForm
          fields={[{ name: "note", label: words.rejectNote, multiline: true, required: true }]}
          submit={words.rejectSubmit}
          onCancel={() => setMode(null)}
          onSubmit={async ({ note }) => {
            await apply(() => post("/v1/requirements/rule", { ...ref, passed: false, note: note ?? "" }));
            setMode(null);
          }}
        />
      ) : null}
      {mode === null && actions.length > 0 ? (
        <div className="row wrap">
          {actions.includes("accept") ? <ActionButton label={words.accept} of={of} primary disabled={busy} onClick={() => accept(false)} /> : null}
          {doesNotFit ? <ActionButton label={words.acceptAnyway} of={of} disabled={busy} onClick={() => accept(true)} /> : null}
          {actions.includes("decline") ? <ActionButton label={words.decline} of={of} onClick={() => setMode("decline")} /> : null}
          {actions.includes("pass") ? (
            <ActionButton
              label={words.pass}
              of={of}
              primary
              disabled={busy}
              onClick={() => void run(() => post("/v1/requirements/rule", { ...ref, passed: true }))}
            />
          ) : null}
          {actions.includes("reject") ? <ActionButton label={words.reject} of={of} onClick={() => setMode("reject")} /> : null}
          {actions.includes("estimate") ? <ActionButton label={words.changeEstimate} of={of} onClick={() => setMode("estimate")} /> : null}
          {actions.includes("cut") ? <ActionButton label={words.cut} of={of} onClick={() => setMode("cut")} /> : null}
          {actions.includes("reopen") ? (
            <ActionButton
              label={words.reopen}
              of={of}
              disabled={busy}
              onClick={() => void run(() => post("/v1/requirements/reopen", ref))}
            />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
