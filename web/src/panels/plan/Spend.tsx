/** Real-world spend: the monthly cap, what is committed, when a purchase needs approval, and the purchases. */
import { get } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { formatDateTime, formatNumber } from "../../lib/format";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { AgentText } from "../board/parts";
import { Section, StateTag, type PlanTabProps } from "./parts";

export function Spend({ projectId, plan }: Pick<PlanTabProps, "projectId" | "plan">): JSX.Element {
  const words = t.decisions.spend;
  // The plan is loaded again on every change in the project; spend follows it.
  const spend = useLoad(() => get("/v1/spend/show", { project_id: projectId }), [projectId, plan]);
  const view = spend.data;
  const money = (amount: number): string => words.money(formatNumber(amount), view?.currency ?? "");
  return (
    <Section title={words.title} testId="spend">
      <ErrorNote error={spend.error} />
      {view && !view.enabled ? <p data-testid="spend-off">{words.off}</p> : null}
      {view?.enabled ? (
        <>
          <dl className="pairs">
            <div>
              <dt>{words.cap}</dt>
              <dd>{money(view.monthly_cap)}</dd>
            </div>
            <div>
              <dt>{words.committed}</dt>
              <dd>{money(view.committed_this_month)}</dd>
            </div>
            <div>
              <dt>{words.approvalAt}</dt>
              <dd>{money(view.approval_at)}</dd>
            </div>
          </dl>
          {view.purchases.length === 0 ? <p className="quiet">{words.noPurchases}</p> : null}
          <ul className="records plain" aria-label={words.purchases}>
            {view.purchases.map((purchase) => (
              <li key={purchase.id} data-testid="purchase">
                <p className="record-text">
                  <AgentText text={purchase.what} /> · {money(purchase.amount)}
                </p>
                <p className="quiet row wrap">
                  <StateTag state={purchase.state} />
                  <span>{words.declared(formatDateTime(purchase.declared_at))}</span>
                </p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </Section>
  );
}
