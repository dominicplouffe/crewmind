/** An agent's proposal (CHAT-7): what it will do, its estimate, and Do it / Not now / Edit. */
import { Check, Coins, Lightbulb, Pencil, ShieldAlert, Undo2, X } from "lucide-react";
import { useId, useState } from "react";
import type { Card } from "../api/client";
import { tokens } from "../lib/humanize";
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

  if (!card) return <p className="quiet action-card is-loading">{t.cards.loading}</p>;

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
    <section
      className={`action-card ${card.state === "open" ? "is-open" : "is-closed"}`}
      aria-label={t.cards.label(card.by)}
      data-testid="action-card"
    >
      <div className="action-card-top">
        <span className="badge badge-accent">
          <Lightbulb size={12} aria-hidden="true" />
          {t.cards.eyebrow}
        </span>
        <span className="quiet">{t.cards.proposedBy(card.by)}</span>
      </div>
      <p className="card-what">{card.what}</p>
      <p className="action-card-meta">
        <span>
          <Coins size={14} aria-hidden="true" /> {t.cards.estimate(tokens(card.estimated_tokens))}
        </span>
        <span className={card.reversible ? "" : "is-final"}>
          {card.reversible ? <Undo2 size={14} aria-hidden="true" /> : <ShieldAlert size={14} aria-hidden="true" />}{" "}
          {card.reversible ? t.cards.reversible : t.cards.notReversible}
        </span>
      </p>
      {card.state !== "open" ? (
        <p className={`card-state state-${card.state}`} role="status">
          {card.state === "accepted" ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}
          {card.state === "accepted" ? t.cards.accepted : card.state === "dismissed" ? t.cards.dismissed : card.state}
        </p>
      ) : editing ? (
        <div className="card-edit">
          <label htmlFor={id}>{t.cards.editLabel}</label>
          <textarea id={id} rows={3} value={text} autoFocus onChange={(event) => setText(event.target.value)} />
          <div className="card-buttons">
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
        <div className="card-buttons">
          <button type="button" className="button primary" disabled={busy} onClick={() => void run(() => onAccept(card.id))}>
            <Check size={15} aria-hidden="true" />
            {t.cards.accept}
          </button>
          <button type="button" className="button" disabled={busy} onClick={() => void run(() => onDismiss(card.id))}>
            {t.cards.dismiss}
          </button>
          <button
            type="button"
            className="button ghost"
            disabled={busy}
            onClick={() => {
              setText(card.what);
              setEditing(true);
            }}
          >
            <Pencil size={14} aria-hidden="true" />
            {t.cards.edit}
          </button>
        </div>
      )}
    </section>
  );
}
