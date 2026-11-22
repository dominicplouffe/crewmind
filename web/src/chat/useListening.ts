/**
 * What the chairman can do to a message (CHAT-8): pin it as a standing order, mark it as an example,
 * say "not what I asked", decide; and answer an agent's proposed order or reopen request.
 * Every rule is the server's: this only calls it and shows what comes back.
 */
import { useCallback, useMemo, useRef, useState } from "react";
import { post, type Message, type Order } from "../api/client";
import type { ChatState } from "./state";
import type { ChatActions } from "./useProjectChat";

export type ListeningDialog =
  | { kind: "order"; order: Order }
  | { kind: "fix"; message: Message }
  | { kind: "decide"; message: Message };

export interface ListeningHandlers {
  onPin(message: Message): void;
  onExample(message: Message, mark: boolean): void;
  onFix(message: Message): void;
  onDecide(message: Message): void;
  onOrder(orderId: number, action: "confirm" | "edit" | "discard"): void;
  onRequest(requestId: number, approve: boolean): void;
}

export interface Listening {
  dialog: ListeningDialog | null;
  close(): void;
  handlers: ListeningHandlers;
  /** These three reject with the server's refusal, which the open dialog shows. */
  confirmOrder(order: Order, text: string): Promise<void>;
  discardOrder(order: Order): Promise<void>;
  sendFix(message: Message, words: string): Promise<void>;
  sendDecision(text: string): Promise<void>;
}

export function useListening(projectId: string, state: ChatState, actions: ChatActions): Listening {
  const [dialog, setDialog] = useState<ListeningDialog | null>(null);
  const orders = useRef(state.orders);
  orders.current = state.orders;
  const close = useCallback(() => setDialog(null), []);

  const settle = useCallback(
    (order: Order) => {
      actions.setOrder(order);
      if (order.note) actions.say(order.note);
      actions.refresh();
    },
    [actions],
  );

  const handlers = useMemo<ListeningHandlers>(
    () => ({
      onPin(message) {
        post("/v1/orders/pin", { project_id: projectId, what: String(message.id) })
          .then((order) => {
            settle(order);
            if (order.state === "proposed") setDialog({ kind: "order", order });
          })
          .catch(actions.reportError);
      },
      onExample(message, mark) {
        const call = mark
          ? post("/v1/examples/mark", { project_id: projectId, what: String(message.id) })
          : post("/v1/examples/unmark", { project_id: projectId, message_id: message.id });
        call
          .then((result) => {
            actions.setExample(result.message_id, result.is_example);
            actions.refresh();
          })
          .catch(actions.reportError);
      },
      onFix: (message) => setDialog({ kind: "fix", message }),
      onDecide: (message) => setDialog({ kind: "decide", message }),
      onOrder(orderId, action) {
        if (action === "edit") {
          const order = orders.current[orderId];
          if (order) setDialog({ kind: "order", order });
          return;
        }
        post(`/v1/orders/${action}`, { project_id: projectId, order_id: orderId }).then(settle).catch(actions.reportError);
      },
      onRequest(requestId, approve) {
        post("/v1/decisions/answer", { project_id: projectId, request_id: requestId, approve })
          .then((decision) => {
            if (decision.note) actions.say(decision.note);
            actions.refresh();
          })
          .catch(actions.reportError);
      },
    }),
    [actions, projectId, settle],
  );

  return {
    dialog,
    close,
    handlers,
    async confirmOrder(order, text) {
      const edited = text.trim() === order.text ? undefined : text;
      settle(await post("/v1/orders/confirm", { project_id: projectId, order_id: order.id, text: edited }));
      close();
    },
    async discardOrder(order) {
      settle(await post("/v1/orders/discard", { project_id: projectId, order_id: order.id }));
      close();
    },
    async sendFix(message, words) {
      const correction = await post("/v1/corrections/record", { project_id: projectId, words, message_id: message.id });
      if (correction.note) actions.say(correction.note);
      actions.refresh();
      close();
    },
    async sendDecision(text) {
      const decision = await post("/v1/decisions/decide", { project_id: projectId, text });
      if (decision.note) actions.say(decision.note);
      actions.refresh();
      close();
    },
  };
}
