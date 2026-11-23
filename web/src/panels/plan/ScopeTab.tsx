/** Scope: the requirements by stage and the longest chain; bets for an Explore project; cycles for an Operate one. */
import { ListTodo } from "lucide-react";
import { useState } from "react";
import { Empty } from "../kit";
import { t } from "../../strings";
import { AddRequirement } from "./AddRequirement";
import { Bets } from "./Bets";
import { Cycles } from "./Cycles";
import { groupByStage, isSettled } from "./logic";
import { Section, type PlanTabProps } from "./parts";
import { RequirementRow } from "./RequirementRow";

function LongestChain({ plan }: Pick<PlanTabProps, "plan">): JSX.Element | null {
  const words = t.plan.scope;
  const chain = plan.longest_chain;
  if (plan.requirements.length === 0) return null;
  return (
    <Section title={words.chain} testId="longest-chain">
      {chain.requirements.length === 0 ? (
        <p className="quiet">{words.chainNone}</p>
      ) : (
        <>
          <ol className="chain plain" aria-label={words.chainLabel}>
            {chain.requirements.map((id) => (
              <li key={id}>{words.name(id)}</li>
            ))}
          </ol>
          <p className="quiet" data-testid="chain-runs">
            {words.chainHint(chain.runs)}
          </p>
        </>
      )}
    </Section>
  );
}

export function ScopeTab(props: PlanTabProps): JSX.Element {
  const { plan, type } = props;
  const [adding, setAdding] = useState(false);
  const words = t.plan.scope;

  if (type === "explore") return <Bets {...props} />;

  const groups = groupByStage(plan.requirements);
  return (
    <>
      {plan.requirements.length === 0 && !adding ? <Empty icon={ListTodo} title={words.emptyTitle} next={words.emptyNext} /> : null}
      {groups.map((group) => (
        <section key={group.stage} data-testid="stage" data-stage={group.stage}>
          <h3 className="group-title">
            {words.stage(group.stage)}
            {plan.lowest_open_stage === group.stage ? <span className="quiet"> · {words.stageOpen}</span> : null}
          </h3>
          <ul className="records plain" aria-label={words.listLabel(group.stage)}>
            {group.rows.map((requirement) => (
              <RequirementRow
                key={requirement.id}
                {...props}
                requirement={requirement}
                multiplier={plan.numbers.bias_multiplier}
              />
            ))}
          </ul>
        </section>
      ))}
      <LongestChain plan={plan} />
      {adding ? (
        <AddRequirement
          {...props}
          others={plan.requirements.filter((requirement) => !isSettled(requirement.state))}
          onDone={() => setAdding(false)}
        />
      ) : (
        <button type="button" className="button small primary plan-add" onClick={() => setAdding(true)}>
          {words.add.open}
        </button>
      )}
      {type === "operate" ? <Cycles {...props} /> : null}
    </>
  );
}
