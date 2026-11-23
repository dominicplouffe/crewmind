/** Pieces the Plan tabs share: the tab props, a state tag, a section, a confirmation and a small form. */
import { useId, useState, type FormEvent, type ReactNode } from "react";
import type { Schemas } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { t } from "../../strings";
import { Pill, type Tone } from "../../ui/Status";

export type PlanView = Schemas["PlanView"];
export type Requirement = Schemas["RequirementItem"];

/** Sends one change to the server. Every change answers with the whole plan again. */
export type Change = () => Promise<PlanView>;

export interface PlanTabProps {
  projectId: string;
  plan: PlanView;
  /** The project's type (explore, deliver, operate) and state, as the server names them. */
  type: string;
  state: string;
  busy: boolean;
  /** The last refusal of a button press, for an action that offers another way after being refused. */
  refusal: unknown;
  /** Runs a change from a button. A refusal is shown above the tabs; resolves true when it worked. */
  run(change: Change): Promise<boolean>;
  /** Runs a change from a form. A refusal is thrown, so the form shows it and keeps what was typed. */
  apply(change: Change): Promise<void>;
}

/** The tone of a plan state's dot. The word beside it carries the meaning. */
export function stateTone(state: string): Tone {
  switch (state) {
    case "met":
    case "confirmed":
    case "kept":
      return "success";
    case "in progress":
    case "accepted":
    case "active":
    case "open":
      return "accent";
    case "checking":
    case "proposed":
      return "info";
    case "breached":
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

/** A state as a pill with a plain word. The server's state is kept for screen readers and tests. */
export function StateTag({ state }: { state: string }): JSX.Element {
  return (
    <span className="state-tag" data-testid="state-tag">
      <Pill tone={stateTone(state)}>
        <span className="visually-hidden">{t.plan.stateOf}: </span>
        <span className="cap">{t.plan.states[state] ?? state}</span>
      </Pill>
    </span>
  );
}

/** A titled part of a tab. */
export function Section({ title, testId, children }: { title: string; testId?: string; children: ReactNode }): JSX.Element {
  const id = useId();
  return (
    <section className="plan-section" aria-labelledby={id} data-testid={testId}>
      <h3 className="group-title" id={id}>
        {title}
      </h3>
      {children}
    </section>
  );
}

interface ConfirmProps {
  question: string;
  yes: string;
  busy: boolean;
  onYes(): void;
  onCancel(): void;
}

/** Asks before something that cannot simply be taken back. */
export function Confirm({ question, yes, busy, onYes, onCancel }: ConfirmProps): JSX.Element {
  return (
    <div className="item-confirm" role="group" aria-label={question}>
      <p>{question}</p>
      <div className="row wrap">
        <button type="button" className="button small primary" disabled={busy} onClick={onYes}>
          {yes}
        </button>
        <button type="button" className="button small" onClick={onCancel}>
          {t.common.cancel}
        </button>
      </div>
    </div>
  );
}

export interface FormField {
  name: string;
  label: string;
  type?: "text" | "number" | "date" | "datetime-local";
  multiline?: boolean;
  required?: boolean;
  initial?: string;
  hint?: string;
}

interface FieldsFormProps {
  fields: FormField[];
  submit: string;
  /** Resolves when the server accepted it; rejects with its refusal. */
  onSubmit(values: Record<string, string>): Promise<unknown>;
  onCancel(): void;
}

/** A few labelled fields with one button. The first field takes focus; a refusal is shown as given. */
export function FieldsForm({ fields, submit, onSubmit, onCancel }: FieldsFormProps): JSX.Element {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((field) => [field.name, field.initial ?? ""])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const id = useId();

  const send = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(values);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="text-form" onSubmit={(event) => void send(event)}>
      {fields.map((field, index) => {
        const shared = {
          id: `${id}-${field.name}`,
          value: values[field.name] ?? "",
          required: field.required,
          autoFocus: index === 0,
          "aria-describedby": field.hint ? `${id}-${field.name}-hint` : undefined,
          onChange: (event: { target: { value: string } }) => setValues((old) => ({ ...old, [field.name]: event.target.value })),
        };
        return (
          <div key={field.name} className="form-field">
            <label htmlFor={shared.id}>{field.label}</label>
            {field.multiline ? (
              <textarea rows={3} {...shared} />
            ) : (
              <input type={field.type ?? "text"} min={field.type === "number" ? 1 : undefined} {...shared} />
            )}
            {field.hint ? (
              <p className="quiet" id={`${id}-${field.name}-hint`}>
                {field.hint}
              </p>
            ) : null}
          </div>
        );
      })}
      <ErrorNote error={error} />
      <div className="row wrap">
        <button type="submit" className="button small primary" disabled={busy}>
          {submit}
        </button>
        <button type="button" className="button small" onClick={onCancel}>
          {t.common.cancel}
        </button>
      </div>
    </form>
  );
}

/** A button whose visible word is short and whose full name says what it acts on. */
export function ActionButton({
  label,
  of,
  primary,
  disabled,
  onClick,
}: {
  label: string;
  of: string;
  primary?: boolean;
  disabled?: boolean;
  onClick(): void;
}): JSX.Element {
  return (
    <button type="button" className={primary ? "button small primary" : "button small"} disabled={disabled} onClick={onClick}>
      {label}
      <span className="visually-hidden"> {of}</span>
    </button>
  );
}
