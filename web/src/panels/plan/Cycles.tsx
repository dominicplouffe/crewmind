/** Operate: each cycle with what it achieved and the account of it. */
import { useState } from "react";
import { post } from "../../api/client";
import { Empty } from "../../components/common";
import { formatDateTime, formatNumber } from "../../lib/format";
import { t } from "../../strings";
import { AgentText } from "../board/parts";
import { readScorecard, toMoment } from "./logic";
import { FieldsForm, Section, StateTag, type PlanTabProps } from "./parts";

export function Cycles({ projectId, plan, apply }: PlanTabProps): JSX.Element {
  const [settingDue, setSettingDue] = useState(false);
  const words = t.plan.scope.cycles;
  const cycles = [...plan.cycles].sort((left, right) => right.number - left.number);

  return (
    <Section title={words.title} testId="cycles">
      {cycles.length === 0 ? <Empty title={words.emptyTitle} next={words.emptyNext} /> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {cycles.map((cycle) => {
          const card = readScorecard(cycle.scorecard);
          return (
            <li key={cycle.number} data-testid="cycle" className={cycle.state === "open" ? "" : "is-past"}>
              <p className="record-text">{words.name(cycle.number)}</p>
              <p className="quiet row wrap">
                <StateTag state={cycle.state} />
                <span>{words.span(formatDateTime(cycle.opened_at), formatDateTime(cycle.ends_at))}</span>
              </p>
              <p className="quiet">{words.due(formatDateTime(cycle.due_at))}</p>
              <p data-testid="cycle-scorecard">
                {card
                  ? words.scorecard(card.recurringMet, card.recurringTotal, card.workRuns, formatNumber(card.tokens))
                  : words.noScorecard}
              </p>
              {cycle.narrative ? (
                <p>
                  <span className="quiet">{cycle.narrative_by_ceo ? words.narrativeByCeo : words.narrativeByPlatform}: </span>
                  <AgentText text={cycle.narrative} />
                </p>
              ) : null}
              {cycle.state !== "open" ? null : settingDue ? (
                <FieldsForm
                  fields={[
                    { name: "due", label: words.dueAt, type: "datetime-local", required: true },
                    { name: "source", label: words.dueSource, required: true },
                  ]}
                  submit={words.dueSubmit}
                  onCancel={() => setSettingDue(false)}
                  onSubmit={async ({ due, source }) => {
                    await apply(() =>
                      post("/v1/cycles/set_due", { project_id: projectId, due_at: toMoment(due ?? "") ?? "", source: source ?? "" }),
                    );
                    setSettingDue(false);
                  }}
                />
              ) : (
                <button type="button" className="button small" onClick={() => setSettingDue(true)}>
                  {words.setDue}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
