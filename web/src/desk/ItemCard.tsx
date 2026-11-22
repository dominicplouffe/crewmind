/**
 * A decision item as a card (HUM-1, HUM-2): the decision, who asks, by when, what is recommended,
 * what happens if nobody answers, and the buttons. The chat shows it on the item's own line; the
 * Desk shows the same card. Every word about the item comes from the server; this only arranges it.
 */
import { MessageSquare, Sparkles } from "lucide-react";
import { useContext, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { Avatar } from "../ui/Avatar";
import { Skeleton } from "../ui/Skeleton";
import { ItemsContext } from "./context";
import { ItemActions } from "./ItemActions";
import { ItemBody, ItemFields } from "./ItemFields";
import type { Item } from "./logic";
import { askerOf, deadlineWords, kindLabel } from "./when";

interface Props {
  item: Item;
  /** Called after the person decided, noted or changed something on the item. */
  onChanged(item: Item): void;
}

export function ItemCard({ item: given, onChanged }: Props): JSX.Element {
  const words = t.decisions.card;
  const inChat = useContext(ItemsContext) !== null;
  // The server's answer to a button press is shown at once; the next load replaces it.
  const [answered, setAnswered] = useState<Item | null>(null);
  useEffect(() => setAnswered(null), [given]);
  const item = answered ?? given;
  const open = item.actions.length > 0;
  const closed = item.closed_at !== null || item.outcome !== null;
  const asker = askerOf(item.filed_by, item.kind);
  const when = deadlineWords(item.deadline, item.default_outcome);
  const urgent = open && (when.urgency === "overdue" || when.urgency === "today");
  const stateWord = t.decisions.states[item.state] ?? item.state;

  const changed = (view: Item): void => {
    setAnswered(view);
    onChanged(view);
  };

  return (
    <section
      className={`item-card ${open ? "is-open" : "is-closed"} ${urgent ? `is-${when.urgency}` : ""}`}
      aria-label={words.label(item.title)}
      data-testid="item-card"
      data-item-id={item.id}
      data-item-kind={item.kind}
    >
      <div className="item-top">
        <span className="badge item-kind">
          <span className="visually-hidden">{words.kind}: </span>
          {kindLabel(item.kind)}
        </span>
        {open && when.badge ? <span className={`badge urgency urgency-${when.urgency}`}>{when.badge}</span> : null}
        {/* "open" goes without saying on a card that asks; it stays for screen readers. */}
        <span className={item.state === "open" ? "visually-hidden" : "badge item-state"} data-testid="item-state">
          <span className="visually-hidden">{words.stateOf}: </span>
          <span className="cap">{stateWord}</span>
        </span>
      </div>
      <h3 className="item-title">
        <AgentText text={item.title} />
      </h3>
      <ItemBody item={item} />
      <p className="item-asker">
        {asker.name ? (
          <Avatar name={asker.name} kind="agent" size="xs" />
        ) : (
          <Sparkles size={14} aria-hidden="true" className="asker-icon" />
        )}
        <span>{asker.line}</span>
      </p>
      {open ? (
        <p className={`item-deadline urgency-${when.urgency}`} data-testid="item-deadline">
          {when.line}
        </p>
      ) : null}
      {item.recommendation ? (
        <div className="item-recommendation">
          <span className="item-label">{words.recommendation}</span>
          <p>
            <AgentText text={item.recommendation} />
          </p>
        </div>
      ) : null}
      {open && when.ifNothing ? (
        <p className="item-default" data-testid="item-default">
          {when.ifNothing}
        </p>
      ) : null}
      {item.if_declined ? (
        <p className="quiet item-if-declined">
          <span className="item-label-inline">{words.ifDeclined}: </span>
          <AgentText text={item.if_declined} />
        </p>
      ) : null}
      <ItemFields item={item} onChanged={changed} />
      {open ? null : closed ? (
        <p className="item-outcome" role="status" data-testid="item-outcome">
          {item.outcome ? (
            <>
              <span className="item-label-inline">{words.outcome}: </span>
              <AgentText text={item.outcome} />
            </>
          ) : (
            words.noOutcome(stateWord)
          )}
        </p>
      ) : (
        <p className="quiet">{words.openNoActions}</p>
      )}
      {item.chairman_note ? (
        <p className="item-note">
          <span className="item-label-inline">{words.yourNote}: </span>
          <AgentText text={item.chairman_note} />
        </p>
      ) : null}
      <ItemActions item={item} onChanged={changed} />
      {!inChat ? (
        <p className="item-discuss">
          <Link to={`/projects/${item.project_id}`} className="button small ghost">
            <MessageSquare size={14} aria-hidden="true" />
            {t.decisions.desk.discuss}
            <span className="visually-hidden"> {words.of(item.title)}</span>
          </Link>
        </p>
      ) : null}
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
    return item.error ? (
      <ErrorNote error={item.error} />
    ) : (
      <div className="item-card is-loading">
        <Skeleton lines={3} label={t.decisions.card.loading} />
      </div>
    );
  }
  return <ItemCard item={item.data} onChanged={() => scope?.onChanged()} />;
}
