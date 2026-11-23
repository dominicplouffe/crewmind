/** Replacing a secret's value (CON-2). The field is empty, masked, and cleared once saved. */
import { useId, useRef, useState, type FormEvent } from "react";
import { post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { Modal } from "../components/Modal";
import { connectionWords as words } from "../strings.connections";

interface Props {
  item: Schemas["ConnectionView"];
  onClose(): void;
  onDone(): void;
}

export function ReplaceDialog({ item, onClose, onDone }: Props): JSX.Element {
  const id = useId();
  // The value lives only in the field, never in React state or a DOM attribute (CON-15).
  const field = useRef<HTMLInputElement>(null);
  const [filled, setFilled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    post("/v1/connections/replace_secret", { connection: item.id, value: field.current?.value ?? "" })
      .then(() => {
        if (field.current) field.current.value = "";
        onDone();
      })
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };
  return (
    <Modal title={words.replaceTitle(item.name)} testId="replace-secret" onClose={onClose}>
      <form className="modal-form" onSubmit={submit} autoComplete="off">
        <p className="quiet">{words.replaceHelp}</p>
        <label htmlFor={id}>{words.form.value}</label>
        <input
          id={id}
          ref={field}
          type="password"
          onInput={(event) => setFilled(event.currentTarget.value.length > 0)}
          required
          autoComplete="new-password"
          spellCheck={false}
          data-1p-ignore
          data-lpignore="true"
          autoFocus
        />
        <ErrorNote error={error} />
        <div className="modal-actions">
          <button type="button" className="button" onClick={onClose} disabled={busy}>
            {words.form.cancel}
          </button>
          <button type="submit" className="button primary" disabled={busy || !filled}>
            {busy ? words.form.saving : words.replace}
          </button>
        </div>
      </form>
    </Modal>
  );
}
