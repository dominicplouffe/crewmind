/** Dates and budget: the projection, the commitment and target beside it, the CEO's reserve and requests for more. */
import { formatDateTime, formatNumber } from "../../lib/format";
import { t } from "../../strings";
import { Commitment } from "./Commitment";
import { Section, type PlanTabProps } from "./parts";
import { Raises, Reserve } from "./Reserve";
import { Target } from "./Target";

function Projection({ plan }: Pick<PlanTabProps, "plan">): JSX.Element {
  const words = t.plan.dates;
  const { pace, numbers } = plan;
  return (
    <Section title={words.projection} testId="projection">
      <p className="record-text" data-testid="projection-text">
        {pace.projection}
      </p>
      <p className="quiet" data-testid="projection-kind">
        {words.kinds[pace.projection_kind] ?? pace.projection_kind}
      </p>
      <dl className="pairs">
        <div>
          <dt>{words.projectedAt}</dt>
          <dd>{pace.projected_at ? formatDateTime(pace.projected_at) : t.plan.unknown}</dd>
        </div>
        <div>
          <dt>{words.remaining}</dt>
          <dd>{words.remainingValue(numbers.remaining_runs, numbers.unestimated)}</dd>
        </div>
        {numbers.bias_multiplier > 1 ? (
          <div>
            <dt>{words.multiplier}</dt>
            <dd>{words.multiplierValue(formatNumber(numbers.bias_multiplier))}</dd>
          </div>
        ) : null}
        <div>
          <dt>{words.throughput}</dt>
          <dd>{pace.throughput == null ? words.notMeasured : words.throughputValue(formatNumber(pace.throughput))}</dd>
        </div>
        <div>
          <dt>{words.burnRate}</dt>
          <dd>{pace.burn_rate == null ? words.notMeasured : words.burnRateValue(formatNumber(pace.burn_rate))}</dd>
        </div>
        <div>
          <dt>{words.projectedSpend}</dt>
          <dd>{pace.projected_spend == null ? t.plan.unknown : t.plan.tokens(formatNumber(pace.projected_spend))}</dd>
        </div>
        <div>
          <dt>{words.planTokens}</dt>
          <dd data-testid="plan-tokens">{numbers.plan_tokens_text}</dd>
        </div>
        <div>
          <dt>{words.beforeWrapup}</dt>
          <dd>{t.plan.tokens(formatNumber(numbers.tokens_before_wrapup))}</dd>
        </div>
      </dl>
    </Section>
  );
}

export function DatesTab(props: PlanTabProps): JSX.Element {
  return (
    <>
      <Projection plan={props.plan} />
      <Commitment {...props} />
      <Target {...props} />
      <Reserve {...props} />
      <Raises {...props} />
    </>
  );
}
