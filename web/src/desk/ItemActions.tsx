/** The buttons of a decision item. An action that needs an input or a second thought asks for it first. */
import { Clock, StickyNote } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { ApiError, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { AgentText } from "../panels/board/parts";
import { FieldsForm, type FormField } from "../panels/plan/parts";
import { formatValue } from "../lib/format";
import { t } from "../strings";
import {
  asksFirst,
  canExtend,
  decideBody,
  listField,
  needsOf,
  numberField,
  textField,
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

/** A question's options as a radio list, with room for an answer in the person's own words. */
function AnswerForm({ item, onChanged }: Props): JSX.Element {
  const words = t.decisions.question;
  const options = listField(item.fields, "options");
  const recommended = numberField(item.fields, "recommended");
  const ceoDefault = textField(item.fields, "default");
  const [option, setOption] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const id = useId();

  const send = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onChanged(await decide(item, "answer", { option, note }));
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="text-form" onSubmit={(event) => void send(event)} data-testid="answer-form">
      {options.length > 0 ? (
        <fieldset className="plan-fieldset answer-options">
          <legend>{words.options}</legend>
          {options.map((text, index) => (
            <p key={index} className="answer-option">
              <input
                type="radio"
                id={`${id}-${index}`}
                name={`${id}-option`}
                checked={option === index + 1}
                onChange={() => setOption(index + 1)}
              />{" "}
              <label htmlFor={`${id}-${index}`}>
                <AgentText text={words.option(index + 1, formatValue(text))} />
                {recommended === index + 1 ? <span className="badge badge-accent"> {words.recommended}</span> : null}
              </label>
            </p>
          ))}
        </fieldset>
      ) : null}
      {ceoDefault ? <p className="quiet">{words.ceoDefault(ceoDefault)}</p> : null}
      <label htmlFor={`${id}-note`}>{words.note}</label>
      <textarea id={`${id}-note`} rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
      <ErrorNote error={error} />
      <div className="row wrap">
        <button type="submit" className="button primary" disabled={busy}>
          {t.decisions.card.actions.answer}
          <span className="visually-hidden"> {t.decisions.card.of(item.title)}</span>
        </button>
      </div>
    </form>
  );
}

type Asking = { action: string } | { more: "note" | "extend" } | null;

export function ItemActions({ item, onChanged }: Props): JSX.Element | null {
  const words = t.decisions.card;
  const [asking, setAsking] = useState<Asking>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const actions = item.actions.filter((action) => !needsOf(item.kind, action).answer);
  const answers = actions.length < item.actions.length;
  const name = (action: string): string => words.actions[action] ?? action;

  const press = async (action: string): Promise<void> => {
    setError(null);
    if (asksFirst(needsOf(item.kind, action))) {
      setAsking({ action });
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

  if (item.actions.length === 0) return null;

  let form: JSX.Element | null = null;
  if (asking && "action" in asking) {
    const action = asking.action;
    const question = words.confirm[action];
    form = (
      <div className="item-confirm" role="group" aria-label={question ?? name(action)} data-testid="action-form">
        {question ? <p className="item-confirm-question">{question}</p> : null}
        <FieldsForm
          fields={fieldsFor(item, action)}
          submit={name(action)}
          onCancel={() => setAsking(null)}
          onSubmit={async (values) => {
            const view = await decide(item, action, values);
            setAsking(null);
            onChanged(view);
          }}
        />
      </div>
    );
  } else if (asking?.more === "note") {
    form = (
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
  } else if (asking?.more === "extend") {
    form = (
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
    <div data-testid="item-actions">
      {answers ? <AnswerForm item={item} onChanged={onChanged} /> : null}
      <ErrorNote error={error} />
      {form ?? (
        <div className="item-buttons" role="group" aria-label={words.actionsLabel}>
          {actions.map((action, index) => (
            <button
              key={action}
              type="button"
              className={index === 0 ? "button primary" : "button"}
              disabled={busy}
              onClick={() => void press(action)}
            >
              {name(action)}
              <span className="visually-hidden"> {words.of(item.title)}</span>
            </button>
          ))}
          <span className="item-more">
            <button type="button" className="button small ghost" onClick={() => setAsking({ more: "note" })}>
              <StickyNote size={14} aria-hidden="true" />
              {words.more.note}
              <span className="visually-hidden"> {words.of(item.title)}</span>
            </button>
            {canExtend(item) ? (
              <button type="button" className="button small ghost" onClick={() => setAsking({ more: "extend" })}>
                <Clock size={14} aria-hidden="true" />
                {words.more.extend}
                <span className="visually-hidden"> {words.of(item.title)}</span>
              </button>
            ) : null}
          </span>
        </div>
      )}
    </div>
  );
}
