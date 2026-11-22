/** Pieces the memory tabs share: running a change, a one-field form, a note from the server. */
import { useCallback, useId, useState, type FormEvent } from "react";
import { ErrorNote } from "../../components/common";
import { t } from "../../strings";

export interface TabProps {
  projectId: string;
  /** Changes whenever the project changes, so the tab reloads. */
  changes: number;
  /** Tells the page something changed, so the chat header and other views reload. */
  onChanged(): void;
}

export interface Act {
  busy: boolean;
  error: unknown;
  /** Runs a change. A refusal is kept in `error` to show in the server's words; resolves true when it worked. */
  run(work: () => Promise<unknown>): Promise<boolean>;
}

export function useAct(after: () => void): Act {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = useCallback(
    async (work: () => Promise<unknown>): Promise<boolean> => {
      setBusy(true);
      setError(null);
      try {
        await work();
        after();
        return true;
      } catch (reason) {
        setError(reason);
        return false;
      } finally {
        setBusy(false);
      }
    },
    [after],
  );
  return { busy, error, run };
}

interface TextFormProps {
  label: string;
  submit: string;
  initial?: string;
  multiline?: boolean;
  focus?: boolean;
  /** Resolves when the server accepted it; rejects with its refusal. */
  onSubmit(text: string): Promise<unknown>;
  onCancel?(): void;
}

/** One labelled text field with its button. It empties after a success and shows a refusal as given. */
export function TextForm({ label, submit, initial = "", multiline, focus, onSubmit, onCancel }: TextFormProps): JSX.Element {
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const id = useId();

  const send = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(text);
      setText("");
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  const field = {
    id,
    value: text,
    autoFocus: focus,
    onChange: (event: { target: { value: string } }) => setText(event.target.value),
  };
  return (
    <form className="text-form" onSubmit={(event) => void send(event)}>
      <label htmlFor={id}>{label}</label>
      {multiline ? <textarea rows={3} {...field} /> : <input {...field} />}
      <ErrorNote error={error} />
      <div className="row wrap">
        <button type="submit" className="button small primary" disabled={busy}>
          {submit}
        </button>
        {onCancel ? (
          <button type="button" className="button small" onClick={onCancel}>
            {t.common.cancel}
          </button>
        ) : null}
      </div>
    </form>
  );
}

/** Something the server asked to be shown to the person. */
export function ServerNote({ text }: { text: string | null | undefined }): JSX.Element | null {
  if (!text) return null;
  return (
    <p className="note" role="status" data-testid="server-note">
      {text}
    </p>
  );
}

/** A small tag beside an item: its state, or a mark such as "From outside". */
export function Tag({ children, title }: { children: string; title?: string }): JSX.Element {
  return (
    <span className="marker" title={title}>
      {children}
    </span>
  );
}

export function stateName(names: Record<string, string>, state: string): string {
  return names[state] ?? state;
}
