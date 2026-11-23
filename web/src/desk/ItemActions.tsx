/**
 * The buttons of a decision item. The first action the server lists is the primary button; an action
 * that needs an input or a second thought asks for it first, inline. A question shows its options as
 * a compact choice. Adding a note and giving more time live in the card's details (`ItemMore`).
 */
import { Clock, PenLine, StickyNote, Star } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatValue } from "../lib/format";
import { AgentText } from "../panels/board/parts";
import { FieldsForm, type FormField } from "../panels/plan/parts";
import { t } from "../strings";
import {
  asksFirst,
  canExtend,
  decideBody,
  listField,
  needsOf,
  numberField,
  type ActionValues,
  type Item,
} from "./logic";

interface Props {
  item: Item;
  /** Called with the item as the server answered it. */
  onChanged(item: Item): void;
}

/** Something the person still has to fill in, shown the way a refusal from the server is shown. */
function missing(message: string): ApiError {
  return new ApiError(0, { kind: "input", code: "missing_input", message, rule: null, hint: null }, message);
}

async function decide(item: Item, action: string, values: ActionValues): Promise<Item> {
  const body = decideBody(item, action, values);
  if (typeof body === "string") throw missing(body);
  return post("/v1/items/decide", body);
}

function fieldsFor(item: Item, action: string): FormField[] {
  const needs = needsOf(item.kind, action);
  const words = t.decisions.card.inputs;
  const fields: FormField[] = [];
  if (needs.amount) {
    const required = needs.amount === "required";
    fields.push({ name: "amount", label: required ? words.amount : words.amountOptional, type: "number", required });
  }
  if (needs.date) fields.push({ name: "date", label: words.date, type: "date" });
  if (needs.note) {
    const required = needs.note === "required";
    fields.push({ name: "note", label: required ? words.rejectNote : words.noteOptional, multiline: true, required });
  }
  return fields;
}

/** Whether the item is a question the person can answer now. */
export function answersQuestion(item: Item): boolean {
  return item.actions.some((action) => needsOf(item.kind, action).answer);
}

/**
 * A question's options as a compact choice, the recommended one marked and chosen to start with, and
 * the person's own words behind a link.
 */
function AnswerForm({ item, onChanged, aside }: Props & { aside?: ReactNode }): JSX.Element {
  const words = t.decisions.compact.question;
  const options = listField(item.fields, "options");
  const recommended = numberField(item.fields, "recommended");
  const [option, setOption] = useState<number | null>(recommended !== null && recommended <= options.length ? recommended : null);
  const [own, setOwn] = useState(options.length === 0);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const id = useId();

  const send = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onChanged(await decide(item, "answer", { option, note: own ? note : "" }));
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  const toggleOwn = (): void => {
    // Their own words replace the choice, so it is not sent as well by mistake.
    if (!own) setOption(null);
    else if (option === null && recommended !== null) setOption(recommended);
    setOwn(!own);
  };

  return (
    <form className="dcard-answer" onSubmit={(event) => void send(event)} data-testid="answer-form">
      {options.length > 0 ? (
        <fieldset className="choice">
          <legend className="visually-hidden">{words.choose}</legend>
          {options.map((text, index) => {
            const number = index + 1;
            return (
              <label key={number} className={option === number ? "choice-option is-chosen" : "choice-option"}>
                <input
                  type="radio"
                  className="choice-input"
                  name={`${id}-option`}
                  checked={option === number}
                  onChange={() => setOption(number)}
                />
                <AgentText text={formatValue(text)} />
                {recommended === number ? (
                  <span className="choice-recommended">
                    <Star size={12} aria-hidden="true" />
                    {words.recommended}
                  </span>
                ) : null}
              </label>
            );
          })}
        </fieldset>
      ) : null}
      {own ? (
        <div className="form-field">
          <label htmlFor={`${id}-note`}>{words.ownLabel}</label>
          {/* Opened on request, so it takes focus at once. */}
          <textarea id={`${id}-note`} rows={2} value={note} autoFocus={options.length > 0} onChange={(event) => setNote(event.target.value)} />
        </div>
      ) : null}
      <ErrorNote error={error} />
      <div className="dcard-actions">
        <button type="submit" className="button small primary" disabled={busy}>
          {t.decisions.card.actions.answer}
          <span className="visually-hidden"> {t.decisions.card.of(item.title)}</span>
        </button>
        {options.length > 0 ? (
          <button type="button" className="button small ghost" aria-expanded={own} onClick={toggleOwn}>
            <PenLine size={14} aria-hidden="true" />
            {own ? words.ownHide : words.own}
          </button>
        ) : null}
        {aside}
      </div>
    </form>
  );
}

interface ActionsProps extends Props {
  /** Only the first action, for a slim row (the stack above the chat). */
  only?: "primary";
  /** Placed at the end of the button row, such as the details toggle. */
  aside?: ReactNode;
}

export function ItemActions({ item, onChanged, only, aside }: ActionsProps): JSX.Element | null {
  const words = t.decisions.card;
  const [asking, setAsking] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const name = (action: string): string => words.actions[action] ?? action;

  if (answersQuestion(item) && only !== "primary") return <AnswerForm item={item} onChanged={onChanged} aside={aside} />;

  const all = item.actions.filter((action) => !needsOf(item.kind, action).answer);
  const actions = only === "primary" ? all.slice(0, 1) : all;

  const press = async (action: string): Promise<void> => {
    setError(null);
    if (asksFirst(needsOf(item.kind, action))) {
      setAsking(action);
      return;
    }
    setBusy(true);
    try {
      onChanged(await decide(item, action, {}));
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  if (actions.length === 0) {
    return aside ? <div className="dcard-actions">{aside}</div> : null;
  }

  if (asking) {
    const question = words.confirm[asking];
    return (
      <div className="dcard-confirm" role="group" aria-label={question ?? name(asking)} data-testid="action-form">
        {question ? <p className="dcard-confirm-question">{question}</p> : null}
        <FieldsForm
          fields={fieldsFor(item, asking)}
          submit={name(asking)}
          onCancel={() => setAsking(null)}
          onSubmit={async (values) => {
            const view = await decide(item, asking, values);
            setAsking(null);
            onChanged(view);
          }}
        />
      </div>
    );
  }

  return (
    <div data-testid="item-actions">
      <ErrorNote error={error} />
      <div className="dcard-actions" role="group" aria-label={words.actionsLabel}>
        {actions.map((action, index) => (
          <button
            key={action}
            type="button"
            className={index === 0 ? "button small primary" : "button small"}
            disabled={busy}
            onClick={() => void press(action)}
          >
            {name(action)}
            <span className="visually-hidden"> {words.of(item.title)}</span>
          </button>
        ))}
        {aside}
      </div>
    </div>
  );
}

type More = "note" | "extend" | null;

/** Adding a note and giving more time: the less common things to do with an open item. */
export function ItemMore({ item, onChanged }: Props): JSX.Element {
  const words = t.decisions.card;
  const [asking, setAsking] = useState<More>(null);
  if (asking === "note") {
    return (
      <FieldsForm
        fields={[{ name: "note", label: words.more.noteLabel, multiline: true, required: true }]}
        submit={words.more.noteSave}
        onCancel={() => setAsking(null)}
        onSubmit={async ({ note }) => {
          const view = await post("/v1/items/note", { project_id: item.project_id, item_id: item.id, note: note ?? "" });
          setAsking(null);
          onChanged(view);
        }}
      />
    );
  }
  if (asking === "extend") {
    return (
      <FieldsForm
        fields={[
          { name: "days", label: words.more.extendDays, type: "number", required: true },
          { name: "reason", label: words.more.extendReason, multiline: true, required: true },
        ]}
        submit={words.more.extendSave}
        onCancel={() => setAsking(null)}
        onSubmit={async ({ days, reason }) => {
          const view = await post("/v1/items/extend", {
            project_id: item.project_id,
            item_id: item.id,
            days: Number(days),
            reason: reason ?? "",
          });
          setAsking(null);
          onChanged(view);
        }}
      />
    );
  }
  return (
    <>
      <button type="button" className="button small ghost" onClick={() => setAsking("note")}>
        <StickyNote size={14} aria-hidden="true" />
        {words.more.note}
        <span className="visually-hidden"> {words.of(item.title)}</span>
      </button>
      {canExtend(item) ? (
        <button type="button" className="button small ghost" onClick={() => setAsking("extend")}>
          <Clock size={14} aria-hidden="true" />
          {words.more.extend}
          <span className="visually-hidden"> {words.of(item.title)}</span>
        </button>
      ) : null}
    </>
  );
}
