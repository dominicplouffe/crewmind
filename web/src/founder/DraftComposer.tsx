/** The box for saying more to the Founder (`founder say`). Enter sends; Shift+Enter starts a new line. */
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { t } from "../strings";

interface Props {
  busy: boolean;
  /** Sends the message. Resolves true when the server took it, and the box empties. */
  onSend(body: string): Promise<boolean>;
}

export function DraftComposer({ busy, onSend }: Props): JSX.Element {
  const words = t.founder.talk;
  const [body, setBody] = useState("");

  const send = (): void => {
    const text = body.trim();
    if (!text || busy) return;
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
    <form className="draft-composer" onSubmit={onSubmit}>
      <label htmlFor="draft-message">{words.message}</label>
      <textarea
        id="draft-message"
        rows={2}
        value={body}
        placeholder={words.placeholder}
        aria-describedby="draft-message-hint"
        onChange={(event) => setBody(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="row spread wrap">
        <span className="quiet" id="draft-message-hint">
          {words.sendHint}
        </span>
        <button type="submit" className="button" disabled={busy || body.trim() === ""}>
          {busy ? words.sending : words.send}
        </button>
      </div>
    </form>
  );
}
