/** Explore: the bets being tested, when each is dropped, and the time box they must fit in. */
import { useState } from "react";
import { post } from "../../api/client";
import { Empty } from "../../components/common";
import { formatDateTime } from "../../lib/format";
import { t } from "../../strings";
import { AgentText } from "../board/parts";
import { canExtend, toMoment } from "./logic";
import { ActionButton, FieldsForm, Section, StateTag, type PlanTabProps } from "./parts";

const OPEN_STATES = ["active", "expired"];

export function Bets({ projectId, plan, apply }: PlanTabProps): JSX.Element {
  const [extending, setExtending] = useState<number | null>(null);
  const words = t.plan.scope.bets;
  const box = plan.time_box;

  return (
    <>
      {box ? (
        <Section title={words.timeBox} testId="time-box">
          <p>{words.timeBoxLine(formatDateTime(box.started_at), formatDateTime(box.ends_at))}</p>
          <p className="quiet">{words.newBetsUntil(formatDateTime(box.new_bets_until))}</p>
        </Section>
      ) : null}
      <Section title={words.title}>
        {plan.bets.length === 0 ? <Empty title={words.emptyTitle} next={words.emptyNext} /> : null}
        <ul className="records plain" aria-label={words.listLabel}>
          {plan.bets.map((bet) => (
            <li key={bet.id} data-testid="bet" className={OPEN_STATES.includes(bet.state) ? "" : "is-past"}>
              <p className="record-text">
                <span className="quiet">{words.name(bet.id)}</span> <AgentText text={bet.statement} />
              </p>
              <p className="quiet row wrap">
                <StateTag state={bet.state} />
                <span>{words.killAt(formatDateTime(bet.kill_at))}</span>
              </p>
              <p>
                {words.killCondition}: <AgentText text={bet.kill_condition} />
              </p>
              {bet.extended ? <p className="quiet">{words.extended(bet.extension_reason ?? t.plan.unknown)}</p> : null}
              {bet.finding ? <p data-testid="bet-finding">{words.finding(bet.finding)}</p> : null}
              {canExtend(bet) ? (
                extending === bet.id ? (
                  <FieldsForm
                    fields={[
                      { name: "until", label: words.extendUntil, type: "datetime-local", required: true },
                      { name: "reason", label: words.extendReason, multiline: true, required: true },
                    ]}
                    submit={words.extendSubmit}
                    onCancel={() => setExtending(null)}
                    onSubmit={async ({ until, reason }) => {
                      await apply(() =>
                        post("/v1/bets/extend", {
                          project_id: projectId,
                          bet_id: bet.id,
                          until: toMoment(until ?? "") ?? "",
                          reason: reason ?? "",
                        }),
                      );
                      setExtending(null);
                    }}
                  />
                ) : (
                  <ActionButton label={words.extend} of={words.of(bet.id)} onClick={() => setExtending(bet.id)} />
                )
              ) : null}
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
