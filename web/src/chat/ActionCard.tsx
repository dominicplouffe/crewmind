/** An agent's proposal (CHAT-7): what it will do, its estimate, and Do it / Not now / Edit. */
import { useId, useState } from "react";
import type { Card } from "../api/client";
import { formatNumber } from "../lib/format";
import { t } from "../strings";

interface Props {
  card: Card | undefined;
  onAccept(cardId: number, edited?: string): Promise<void>;
  onDismiss(cardId: number): Promise<void>;
}

export function ActionCard({ card, onAccept, onDismiss }: Props): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const id = useId();

  if (!card) return <p className="quiet">{t.cards.loading}</p>;

  const run = async (work: () => Promise<void>): Promise<void> => {
    setBusy(true);
    try {
      await work();
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="action-card" aria-label={t.cards.label(card.by)} data-testid="action-card">
      <p className="card-what">{card.what}</p>
      <p className="quiet">
        {t.cards.estimate(formatNumber(card.estimated_tokens))}{" "}
        {card.reversible ? t.cards.reversible : t.cards.notReversible}
      </p>
      {card.state !== "open" ? (
        <p className="card-state" role="status">
          {card.state === "accepted" ? t.cards.accepted : card.state === "dismissed" ? t.cards.dismissed : card.state}
        </p>
      ) : editing ? (
        <div className="card-edit">
          <label htmlFor={id}>{t.cards.editLabel}</label>
          <textarea id={id} rows={3} value={text} autoFocus onChange={(event) => setText(event.target.value)} />
          <div className="row">
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={() => void run(() => onAccept(card.id, text))}
            >
              {t.cards.acceptEdited}
            </button>
            <button type="button" className="button" disabled={busy} onClick={() => setEditing(false)}>
              {t.common.cancel}
            </button>
          </div>
        </div>
      ) : (
        <div className="row">
          <button
            type="button"
            className="button primary"
            disabled={busy}
            onClick={() => void run(() => onAccept(card.id))}
          >
            {t.cards.accept}
          </button>
          <button type="button" className="button" disabled={busy} onClick={() => void run(() => onDismiss(card.id))}>
            {t.cards.dismiss}
          </button>
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => {
              setText(card.what);
              setEditing(true);
            }}
          >
            {t.cards.edit}
          </button>
        </div>
      )}
    </section>
  );
}
