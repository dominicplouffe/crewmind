/** The small dialogs behind the message buttons: a proposed standing order, a correction, a decision. */
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { ErrorNote } from "../components/common";
import { Modal } from "../components/Modal";
import { t } from "../strings";
import { snippet } from "./MessageItem";
import type { Listening } from "./useListening";

interface FormProps {
  label: string;
  initial: string;
  submit: string;
  onSubmit(text: string): Promise<void>;
  /** Other buttons beside the submit button; each gets the same busy and error handling. */
  others: { label: string; run?(): Promise<void>; close?: boolean }[];
  onClose(): void;
}

function DialogForm({ label, initial, submit, onSubmit, others, onClose }: FormProps): JSX.Element {
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const id = useId();

  const run = async (work: () => Promise<void>): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (reason) {
      setError(reason);
      setBusy(false);
    }
  };

  return (
    <form
      className="modal-form"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        void run(() => onSubmit(text));
      }}
    >
      <label htmlFor={id}>{label}</label>
      <textarea id={id} rows={4} value={text} onChange={(event) => setText(event.target.value)} />
      <ErrorNote error={error} />
      <div className="row wrap">
        <button type="submit" className="button primary" disabled={busy}>
          {submit}
        </button>
        {others.map((other) => (
          <button
            key={other.label}
            type="button"
            className="button"
            disabled={busy && !other.close}
            onClick={() => (other.run ? void run(other.run) : onClose())}
          >
            {other.label}
          </button>
        ))}
      </div>
    </form>
  );
}

export function ListeningDialogs({ listening }: { listening: Listening }): JSX.Element | null {
  const { dialog, close } = listening;
  if (!dialog) return null;
  let title: string;
  let body: ReactNode;
  switch (dialog.kind) {
    case "order": {
      const order = dialog.order;
      title = t.listening.orderDialog.title;
      body = (
        <>
          <p className="quiet">{t.listening.orderDialog.intro}</p>
          {order.being_shortened ? <p className="note">{t.listening.orderDialog.shortening}</p> : null}
          <DialogForm
            label={t.listening.orderDialog.label}
            initial={order.text}
            submit={t.listening.confirm}
            onSubmit={(text) => listening.confirmOrder(order, text)}
            others={[
              { label: t.listening.discard, run: () => listening.discardOrder(order) },
              { label: t.listening.orderDialog.later, close: true },
            ]}
            onClose={close}
          />
        </>
      );
      break;
    }
    case "fix": {
      const message = dialog.message;
      title = t.listening.fixDialog.title;
      body = (
        <>
          <p className="quiet">{t.listening.fixDialog.intro(message.author)}</p>
          <p className="quiet">
            {t.listening.fixDialog.about} <q>{snippet(message.body)}</q>
          </p>
          <DialogForm
            label={t.listening.fixDialog.label}
            initial=""
            submit={t.listening.fixDialog.submit}
            onSubmit={(words) => listening.sendFix(message, words)}
            others={[{ label: t.common.cancel, close: true }]}
            onClose={close}
          />
        </>
      );
      break;
    }
    case "decide":
      title = t.listening.decideDialog.title;
      body = (
        <>
          <p className="quiet">{t.listening.decideDialog.intro}</p>
          <DialogForm
            label={t.listening.decideDialog.label}
            initial={dialog.message.body}
            submit={t.listening.decideDialog.submit}
            onSubmit={listening.sendDecision}
            others={[{ label: t.common.cancel, close: true }]}
            onClose={close}
          />
        </>
      );
      break;
  }
  return (
    <Modal title={title} testId={`dialog-${dialog.kind}`} onClose={close}>
      {body}
    </Modal>
  );
}
