/**
 * A decision item as a card: what is asked, what is recommended, what happens if nobody answers,
 * and the buttons. The chat shows it on the item's own line; the Desk shows the same card.
 */
import { useContext, useEffect, useState } from "react";
import { get } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { ItemsContext } from "./context";
import { ItemActions } from "./ItemActions";
import { ItemFields } from "./ItemFields";
import { deadlineText, type Item } from "./logic";

interface Props {
  item: Item;
  /** Called after the person decided, noted or changed something on the item. */
  onChanged(item: Item): void;
}

export function ItemCard({ item: given, onChanged }: Props): JSX.Element {
  const words = t.decisions.card;
  // The server's answer to a button press is shown at once; the next load replaces it.
  const [answered, setAnswered] = useState<Item | null>(null);
  useEffect(() => setAnswered(null), [given]);
  const item = answered ?? given;
  const open = item.actions.length > 0;
  const closed = item.closed_at !== null || item.outcome !== null;

  const changed = (view: Item): void => {
    setAnswered(view);
    onChanged(view);
  };

  return (
    <section
      className="action-card item-card"
      aria-label={words.label(item.title)}
      data-testid="item-card"
      data-item-id={item.id}
      data-item-kind={item.kind}
    >
      <p className="card-what">
        <AgentText text={item.title} />
      </p>
      <p className="quiet row wrap">
        <span className="marker">
          <span className="visually-hidden">{words.kind}: </span>
          {item.kind}
        </span>
        <span className="marker" data-testid="item-state">
          <span className="visually-hidden">{words.stateOf}: </span>
          {item.state}
        </span>
      </p>
      {item.recommendation ? (
        <p>
          <span className="item-label">{words.recommendation}: </span>
          <AgentText text={item.recommendation} />
        </p>
      ) : null}
      {item.if_declined ? (
        <p>
          <span className="item-label">{words.ifDeclined}: </span>
          <AgentText text={item.if_declined} />
        </p>
      ) : null}
      <ItemFields item={item} onChanged={changed} />
      {open ? (
        <p data-testid="item-deadline">{deadlineText(item.deadline, item.default_outcome, formatDateTime)}</p>
      ) : closed ? (
        <p className="card-state" role="status" data-testid="item-outcome">
          {item.outcome ? (
            <>
              <span className="item-label">{words.outcome}: </span>
              <AgentText text={item.outcome} />
            </>
          ) : (
            words.noOutcome(item.state)
          )}
        </p>
      ) : (
        <p className="quiet">{words.openNoActions}</p>
      )}
      {item.chairman_note ? (
        <p>
          <span className="item-label">{words.yourNote}: </span>
          <AgentText text={item.chairman_note} />
        </p>
      ) : null}
      <ItemActions item={item} onChanged={changed} />
    </section>
  );
}

/** The card for the item a chat line is about. It loads the item, and reloads while it is still open. */
export function ChatItemCard({ itemId }: { itemId: number }): JSX.Element {
  const scope = useContext(ItemsContext);
  const projectId = scope?.projectId ?? "";
  const [settled, setSettled] = useState(false);
  // A settled item no longer changes, so it is not asked for again on every change in the project.
  const watch = settled ? 0 : (scope?.changes ?? 0);
  const item = useLoad(() => get("/v1/items/show", { project_id: projectId, item_id: itemId }), [projectId, itemId, watch]);
  const closedAt = item.data?.closed_at ?? null;
  useEffect(() => {
    if (closedAt !== null) setSettled(true);
  }, [closedAt]);

  if (!item.data) {
    return item.error ? <ErrorNote error={item.error} /> : <p className="quiet">{t.decisions.card.loading}</p>;
  }
  return <ItemCard item={item.data} onChanged={() => scope?.onChanged()} />;
}
