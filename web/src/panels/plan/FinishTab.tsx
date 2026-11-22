/** Finish: the final gap review, how fast the project moved, the finish action for its type, and the receipt. */
import { useState } from "react";
import { get, post } from "../../api/client";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { useAct } from "../memory/parts";
import { ErrorNote } from "../../components/common";
import { AgentText } from "../board/parts";
import { finishAction, readReceipt, timeRows, type FinishAction } from "./logic";
import { ActionButton, Confirm, FieldsForm, Section, StateTag, type PlanTabProps } from "./parts";
import { Receipt } from "./Receipt";
import { TimeReport } from "./Speed";

const PATHS = {
  sign_off: "/v1/projects/sign_off",
  end: "/v1/projects/end",
  complete: "/v1/projects/complete",
  reopen: "/v1/projects/reopen",
} as const;

function Gaps({ projectId, plan, apply }: PlanTabProps): JSX.Element {
  const [waiving, setWaiving] = useState<number | null>(null);
  const words = t.plan.finish.gaps;
  return (
    <Section title={words.title} testId="gaps">
      <p data-testid="gap-review">{words.review[plan.gap_review] ?? plan.gap_review}</p>
      {plan.gaps.length === 0 ? <p className="quiet">{words.none}</p> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {plan.gaps.map((gap) => (
          <li key={gap.id} data-testid="gap" className={gap.state === "open" ? "" : "is-past"}>
            <p className="record-text">
              <AgentText text={gap.text} />
            </p>
            <p className="quiet row wrap">
              <StateTag state={gap.state} />
              <span className={gap.must_fix ? "badge badge-warning" : "badge"}>{gap.must_fix ? words.mustFix : words.note}</span>
              {gap.requirement_id != null ? <span>{words.requirement(gap.requirement_id)}</span> : null}
            </p>
            {gap.reason ? (
              <p>
                <AgentText text={gap.reason} />
              </p>
            ) : null}
            {gap.waived_reason ? <p>{words.waived(gap.waived_reason)}</p> : null}
            {gap.state !== "open" ? null : waiving === gap.id ? (
              <FieldsForm
                fields={[{ name: "reason", label: words.waiveReason, multiline: true, required: true }]}
                submit={words.waiveSubmit}
                onCancel={() => setWaiving(null)}
                onSubmit={async ({ reason }) => {
                  await apply(() => post("/v1/gaps/waive", { project_id: projectId, gap_id: gap.id, reason: reason ?? "" }));
                  setWaiving(null);
                }}
              />
            ) : (
              <ActionButton label={words.waive} of={words.of(gap.id)} onClick={() => setWaiving(gap.id)} />
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Speed({ plan }: Pick<PlanTabProps, "plan">): JSX.Element {
  const words = t.plan.finish.speed;
  const speed = plan.speed;
  return (
    <Section title={words.title} testId="speed">
      <TimeReport
        toFirstTask={speed.to_first_task_seconds}
        toFirstDeliverable={speed.to_first_deliverable_seconds}
        toDone={speed.to_done_seconds}
        where={timeRows(speed.where)}
      />
      <p className="quiet">{words.flags}</p>
      {speed.flags.length === 0 ? <p className="quiet">{words.noFlags}</p> : null}
      <ul aria-label={words.flagsLabel}>
        {speed.flags.map((flag) => (
          <li key={flag} data-testid="speed-flag">
            {flag}
          </li>
        ))}
      </ul>
    </Section>
  );
}

interface Props extends PlanTabProps {
  changes: number;
  /** Called after the project finished or was reopened, so the plan and the project's state reload. */
  onFinished(): void;
}

export function FinishTab(props: Props): JSX.Element {
  const { projectId, type, state, changes, onFinished } = props;
  const [confirming, setConfirming] = useState<FinishAction | null>(null);
  const receipt = useLoad(() => get("/v1/projects/receipt", { project_id: projectId }), [projectId, changes, state]);
  const { setData } = receipt;
  const act = useAct(onFinished);
  const words = t.plan.finish.action;
  const action = finishAction(type, state);
  const read = receipt.data?.completed ? readReceipt(receipt.data.receipt) : null;

  const finish = (which: FinishAction): Promise<boolean> =>
    act.run(async () => {
      setData(await post(PATHS[which], { project_id: projectId }));
      setConfirming(null);
    });

  return (
    <>
      <Gaps {...props} />
      <Speed plan={props.plan} />
      <Section title={words.title} testId="finish-action">
        <ErrorNote error={act.error} />
        {state === "completed" ? <p data-testid="finish-completed">{words.completed}</p> : null}
        {action === null ? (
          <p className="quiet">{state === "draft" ? words.draft : type === "deliver" ? words.deliverWait : words.other}</p>
        ) : action === "reopen" ? (
          <button type="button" className="button small" disabled={act.busy} onClick={() => void finish("reopen")}>
            {words.reopen}
          </button>
        ) : confirming === action ? (
          <Confirm
            question={words[`${action}Sure`]}
            yes={words[`${action}Yes`]}
            busy={act.busy}
            onCancel={() => setConfirming(null)}
            onYes={() => void finish(action)}
          />
        ) : (
          <button type="button" className="button small primary" onClick={() => setConfirming(action)}>
            {words[action]}
          </button>
        )}
      </Section>
      <ErrorNote error={receipt.error} />
      {read ? <Receipt receipt={read} /> : null}
    </>
  );
}
