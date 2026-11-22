/** Small additions to a message: quiet markers, and the buttons on a proposed order or a reopen request. */
import type { Message, Order, ReopenRequest } from "../api/client";
import { t } from "../strings";
import type { ListeningHandlers } from "./useListening";

export interface MessageDetail {
  kind: string;
  card?: number;
  artifact?: string;
  lint?: string;
  order?: number;
  request?: number;
  /** The decision item a platform line is about. */
  item?: number;
  itemKind?: string;
}

/**
 * Whether a line is an agent's request to reopen a decision. The server files it as a decision item
 * too; in the chat it keeps its own line with Approve and Decline, the same as in the Memory panel.
 */
export function isReopenLine(detail: MessageDetail): boolean {
  if (detail.kind === "reopen request") return true;
  return detail.kind === "decision item" && detail.itemKind === "reopen request" && detail.request !== undefined;
}

export function detailOf(message: Message): MessageDetail {
  const detail = message.detail as Record<string, unknown> | null;
  const text = (key: string): string | undefined => (typeof detail?.[key] === "string" ? (detail[key] as string) : undefined);
  const count = (key: string): number | undefined => (typeof detail?.[key] === "number" ? (detail[key] as number) : undefined);
  return {
    kind: text("kind") ?? "",
    card: count("card"),
    artifact: text("artifact"),
    lint: text("lint"),
    order: count("order"),
    request: count("request"),
    item: count("item"),
    itemKind: text("item_kind"),
  };
}

/** Markers in the message head: an example, crewmind's "long" or "unclear" mark, a held report. */
export function Markers({ detail, example }: { detail: MessageDetail; example: boolean }): JSX.Element {
  const lint = detail.lint ? (t.listening.lint[detail.lint as keyof typeof t.listening.lint] ?? detail.lint) : null;
  return (
    <>
      {example ? (
        <span className="marker" data-testid="marker-example">
          {t.listening.exampleTag}
        </span>
      ) : null}
      {lint ? (
        <span className="marker" data-testid="marker-lint" title={t.listening.lintLabel(lint)}>
          {lint}
        </span>
      ) : null}
      {detail.kind === "held report" ? (
        <span className="marker" data-testid="marker-held">
          {t.listening.heldReport}
        </span>
      ) : null}
    </>
  );
}

interface StatusProps {
  detail: MessageDetail;
  order: Order | undefined;
  request: ReopenRequest | undefined;
  handlers: ListeningHandlers;
}

/** Confirm / Edit / Discard on a proposed order, Approve / Decline on a reopen request, while each is open. */
export function StatusActions({ detail, order, request, handlers }: StatusProps): JSX.Element | null {
  if (detail.kind === "standing order proposed" && order) {
    const name = <span className="visually-hidden"> {t.listening.orderOf(order.id)}</span>;
    if (order.state !== "proposed") {
      const state = t.memory.orders.states[order.state as keyof typeof t.memory.orders.states] ?? order.state;
      return <p className="quiet status-result">{t.listening.orderState(state.toLowerCase())}</p>;
    }
    return (
      <div className="row wrap status-actions" data-testid="order-actions">
        <button type="button" className="button small primary" onClick={() => handlers.onOrder(order.id, "confirm")}>
          {t.listening.confirm}
          {name}
        </button>
        <button type="button" className="button small" onClick={() => handlers.onOrder(order.id, "edit")}>
          {t.listening.edit}
          {name}
        </button>
        <button type="button" className="button small" onClick={() => handlers.onOrder(order.id, "discard")}>
          {t.listening.discard}
          {name}
        </button>
      </div>
    );
  }
  if (isReopenLine(detail) && request) {
    const name = <span className="visually-hidden"> {t.listening.requestOf(request.id)}</span>;
    if (request.approved !== null) {
      return <p className="quiet status-result">{t.listening.requestAnswered(request.approved)}</p>;
    }
    return (
      <div className="row wrap status-actions" data-testid="request-actions">
        <button type="button" className="button small primary" onClick={() => handlers.onRequest(request.id, true)}>
          {t.listening.approve}
          {name}
        </button>
        <button type="button" className="button small" onClick={() => handlers.onRequest(request.id, false)}>
          {t.listening.decline}
          {name}
        </button>
      </div>
    );
  }
  return null;
}
