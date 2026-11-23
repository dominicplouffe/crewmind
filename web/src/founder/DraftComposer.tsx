/**
 * The box for saying something to the Founder (`founder say`). Its label and hint always say
 * whether it can be used now and what it is for: it is the person's turn, there are questions
 * open and this is the way to say something else, or the Founder is working.
 * Enter sends; Shift+Enter starts a new line.
 */
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { t } from "../strings";

export type ComposerMode = "open" | "questions" | "working";

interface Props {
  mode: ComposerMode;
  busy: boolean;
  /** Sends the message. Resolves true when the server took it, and the box empties. */
  onSend(body: string): Promise<boolean>;
}

export function DraftComposer({ mode, busy, onSend }: Props): JSX.Element {
  const words = t.founder.talk;
  const state = words.composer[mode] ?? words.composer.open;
  const [body, setBody] = useState("");
  const locked = mode === "working";

  const send = (): void => {
    const text = body.trim();
    if (!text || busy || locked) return;
    void onSend(text).then((taken) => {
      if (taken) setBody("");
    });
  };

  const onSubmit = (event: FormEvent): void => {
    event.preventDefault();
    send();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  return (
    <form className={`draft-composer composer-${mode}`} onSubmit={onSubmit} data-testid="draft-composer" data-mode={mode}>
      <label htmlFor="draft-message">{state?.label}</label>
      <p className="composer-hint" id="draft-message-hint">
        {state?.hint}
      </p>
      <div className="composer-row">
        <textarea
          id="draft-message"
          rows={mode === "open" ? 2 : 1}
          value={body}
          disabled={locked}
          placeholder={locked ? "" : words.placeholder}
          aria-describedby="draft-message-hint"
          onChange={(event) => setBody(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="button" disabled={busy || locked || body.trim() === ""}>
          {busy ? words.sending : words.send}
        </button>
      </div>
    </form>
  );
}
