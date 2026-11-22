/** A status review: the numbers as they were, the CEO's narrative, and the changes the chairman records. */
import { useState } from "react";
import { post } from "../api/client";
import { formatNumber, formatValue } from "../lib/format";
import { AgentText } from "../panels/board/parts";
import { FieldsForm } from "../panels/plan/parts";
import { t } from "../strings";
import { leversOf, listField, numberField, textField, type Item, type LeverUse } from "./logic";

const LEVERS = ["cut", "add", "reword", "move the date", "raise the budget", "accept the slip"] as const;

function Levers({ title, uses }: { title: string; uses: LeverUse[] }): JSX.Element | null {
  const words = t.decisions.review;
  if (uses.length === 0) return null;
  return (
    <>
      <p className="item-label">{title}</p>
      <ul aria-label={title} data-testid="review-levers">
        {uses.map((use, index) => (
          <li key={index}>{words.leverLine(words.levers[use.lever] ?? use.lever, use.reason)}</li>
        ))}
      </ul>
    </>
  );
}

function LeverForm({ item, onChanged }: { item: Item; onChanged(item: Item): void }): JSX.Element {
  const words = t.decisions.review;
  const [lever, setLever] = useState<string | null>(null);
  if (lever === null) {
    return (
      <div className="row wrap" role="group" aria-label={words.record}>
        <span className="quiet">{words.record}:</span>
        {LEVERS.map((name) => (
          <button key={name} type="button" className="button small" onClick={() => setLever(name)}>
            {words.levers[name]}
          </button>
        ))}
      </div>
    );
  }
  return (
    <div role="group" aria-label={words.levers[lever]}>
      <p className="item-label">{words.levers[lever]}</p>
      <FieldsForm
        fields={[{ name: "reason", label: words.reason, multiline: true, required: true }]}
        submit={words.submit}
        onCancel={() => setLever(null)}
        onSubmit={async ({ reason }) => {
          const view = await post("/v1/reviews/lever", {
            project_id: item.project_id,
            item_id: item.id,
            lever,
            reason: reason ?? "",
          });
          setLever(null);
          onChanged(view);
        }}
      />
    </div>
  );
}

export function ReviewBody({ item, onChanged }: { item: Item; onChanged(item: Item): void }): JSX.Element {
  const words = t.decisions.review;
  const fields = item.fields;
  const numbers = (typeof fields.numbers === "object" && fields.numbers !== null ? fields.numbers : {}) as Record<string, unknown>;
  const requirements = (
    typeof numbers.requirements === "object" && numbers.requirements !== null ? numbers.requirements : {}
  ) as Record<string, unknown>;
  const counts = Object.entries(requirements).map(([state, count]) => words.requirementCount(Number(count), state));
  const flags = listField(numbers, "flags").map(formatValue);
  const amount = (name: string): string => {
    const value = numberField(numbers, name);
    return value === null ? t.plan.unknown : t.decisions.fields.tokens(formatNumber(value));
  };
  const narrative = textField(fields, "narrative");
  const rows: [string, string][] = [
    [words.requirements, counts.length > 0 ? counts.join(", ") : t.plan.none],
    [words.spent, amount("spent")],
    [words.budget, amount("budget")],
    [words.wrapUp, numbers.in_wrap_up === true ? words.yes : words.no],
    [words.commitment, textField(numbers, "commitment") ?? words.noCommitment],
    [words.projection, textField(numbers, "projection") ?? t.plan.unknown],
    [words.failedAudits, formatNumber(numberField(numbers, "failed_audits") ?? 0)],
    [words.flags, flags.length > 0 ? flags.join(", ") : words.noFlags],
  ];
  return (
    <div data-testid="review">
      <p>{fields.green === true ? words.green : words.notGreen}</p>
      <p className="item-label">{words.numbers}</p>
      <dl className="pairs item-fields">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="item-label">{words.narrative}</p>
      <p data-testid="review-narrative">{narrative ? <AgentText text={narrative} /> : words.noNarrative}</p>
      <Levers title={words.previous} uses={leversOf(fields, "previous_levers")} />
      <Levers title={words.used} uses={leversOf(fields, "levers")} />
      {item.actions.length > 0 ? <LeverForm item={item} onChanged={onChanged} /> : null}
    </div>
  );
}
