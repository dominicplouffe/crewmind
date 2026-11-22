/** The fields of a decision item that help decide it. Which fields exist depends on the item's kind. */
import { formatNumber, formatValue } from "../lib/format";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { listField, numberField, textField, type Item } from "./logic";
import { ReviewBody } from "./ReviewBody";

type Row = [label: string, value: string];

/** Kinds whose fields are laid out by name below; any other kind shows its plain fields as they are. */
function knownRows(item: Item): Row[] | null {
  const words = t.decisions.fields;
  const fields = item.fields;
  const rows: Row[] = [];
  const text = (name: string, label: string): void => {
    const value = textField(fields, name);
    if (value) rows.push([label, value]);
  };
  const id = (name: string, label: string): void => {
    const value = numberField(fields, name);
    if (value !== null) rows.push([label, String(value)]);
  };
  const amount = (name: string, label: string, show: (count: string) => string = (count) => count): void => {
    const value = numberField(fields, name);
    if (value !== null) rows.push([label, show(formatNumber(value))]);
  };
  switch (item.kind) {
    case "proposed scope": {
      id("requirement_id", words.requirement);
      const runs = numberField(fields, "estimate_runs");
      if (runs !== null) rows.push([words.estimate, words.runs(runs)]);
      return rows;
    }
    case "verdict":
      id("requirement_id", words.requirement);
      text("success_test", words.successTest);
      return rows;
    case "reserve draw":
      amount("tokens", words.amount, words.tokens);
      text("reason", words.reason);
      return rows;
    case "approval: capacity":
      text("what", words.what);
      amount("amount", words.amount);
      return rows;
    case "audit sample":
      id("task_id", words.task);
      text("label", words.label);
      return rows;
    case "reopen request":
      id("decision_id", words.decision);
      text("reason", words.reason);
      return rows;
    case "question":
      text("why", t.decisions.question.why);
      return rows;
    case "assist":
      text("what", words.what);
      text("step", words.step);
      id("task_id", words.task);
      return rows;
    case "flag": {
      const type = textField(fields, "type");
      if (type) rows.push([words.flagType, words.flag[type] ?? type]);
      text("cause", words.cause);
      return rows;
    }
    case "mistake report":
      text("because", words.because);
      amount("cost_tokens", words.cost, words.tokens);
      text("what_was_wrong", words.wrong);
      text("cause", words.cause);
      text("fix", words.fix);
      text("prevention", words.prevention);
      return rows;
    case "heads-up":
    case "delivery sign-off":
    case "status review":
      return rows;
    default:
      return null;
  }
}

function plainRows(item: Item): Row[] {
  return Object.entries(item.fields)
    .filter(([, value]) => typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    .map(([name, value]) => [name.replace(/_/g, " "), typeof value === "number" ? formatNumber(value) : formatValue(value)]);
}

/** The words the item is about (a proposed requirement, a heads-up), quoted under the title. */
export function ItemBody({ item }: { item: Item }): JSX.Element | null {
  const body = item.kind === "proposed scope" || item.kind === "heads-up" ? textField(item.fields, "text") : null;
  if (!body) return null;
  return (
    <blockquote className="item-body">
      <AgentText text={body} />
    </blockquote>
  );
}

export function ItemFields({ item, onChanged }: { item: Item; onChanged(item: Item): void }): JSX.Element {
  const rows = knownRows(item) ?? plainRows(item);
  const deliverables = item.kind === "delivery sign-off" ? listField(item.fields, "deliverables") : [];
  // An open question lists its options in the answer form; a closed one lists them here.
  const options = item.kind === "question" && !item.actions.includes("answer") ? listField(item.fields, "options") : [];
  const recommended = numberField(item.fields, "recommended");
  return (
    <>
      {rows.length > 0 ? (
        <dl className="pairs item-fields">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                <AgentText text={value} />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {item.kind === "mistake report" && item.state !== "filed" ? <p className="quiet">{t.decisions.fields.notFiled}</p> : null}
      {deliverables.length > 0 ? (
        <ul aria-label={t.decisions.fields.deliverables}>
          {deliverables.map((entry, index) => (
            <li key={index}>
              <AgentText text={formatValue(entry)} />
            </li>
          ))}
        </ul>
      ) : null}
      {options.length > 0 ? (
        <ol aria-label={t.decisions.question.options}>
          {options.map((option, index) => (
            <li key={index}>
              <AgentText text={formatValue(option)} />
              {recommended === index + 1 ? <span className="badge badge-accent"> {t.decisions.question.recommended}</span> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {item.kind === "status review" ? <ReviewBody item={item} onChanged={onChanged} /> : null}
    </>
  );
}
