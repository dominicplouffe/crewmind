/** The project chat's client state and the reducer that updates it. No rules: it stores what arrives. */
import type { Card, Header, Message, Order, ReopenRequest } from "../api/client";
import type { ReplyChunk } from "../api/sse";

export interface PendingMessage {
  key: string;
  body: string;
  replyTo: number | null;
  error: { message: string; hint: string | null } | null;
}

export interface Typing {
  runId: string;
  seat: string;
  text: string;
  updatedAt: number;
}

/** A line the app adds to the chat itself: a command's result or an error. */
export interface Notice {
  key: string;
  kind: "result" | "error";
  title: string;
  text: string;
  hint: string | null;
  data: Record<string, unknown> | null;
  afterMessage: number;
}

export interface ChatState {
  messages: Message[];
  pending: PendingMessage[];
  typing: Typing[];
  notices: Notice[];
  header: Header | null;
  cards: Record<number, Card>;
  /** Standing orders and reopen requests by id, for the buttons on their status lines. */
  orders: Record<number, Order>;
  requests: Record<number, ReopenRequest>;
  /** Example marks set or removed on this page, by message id. */
  examples: Record<number, boolean>;
  /** The id to ask before for the previous page of history; null when the first message is loaded. */
  earlier: number | null;
  delivered: number[];
  loaded: boolean;
  live: boolean;
  changes: number;
}

export const initialState: ChatState = {
  messages: [],
  pending: [],
  typing: [],
  notices: [],
  header: null,
  cards: {},
  orders: {},
  requests: {},
  examples: {},
  earlier: null,
  delivered: [],
  loaded: false,
  live: false,
  changes: 0,
};

export type ChatAction =
  | { type: "reset" }
  | { type: "messages"; items: Message[]; loaded?: boolean }
  | { type: "history"; items: Message[]; earlier: number | null }
  | { type: "listening"; orders: Order[]; requests: ReopenRequest[] }
  | { type: "order"; order: Order }
  | { type: "example"; messageId: number; marked: boolean }
  | { type: "pending"; pending: PendingMessage }
  | { type: "delivered"; key: string; message: Message }
  | { type: "sendFailed"; key: string; message: string; hint: string | null }
  | { type: "dropPending"; key: string }
  | { type: "reply"; chunk: ReplyChunk; at: number }
  | { type: "dropTyping"; runId: string }
  | { type: "pruneTyping"; now: number; quietMs: number }
  | { type: "header"; header: Header }
  | { type: "cards"; cards: Card[] }
  | { type: "card"; card: Card }
  | { type: "notice"; notice: Notice }
  | { type: "dropNotice"; key: string }
  | { type: "live"; live: boolean }
  | { type: "changed" };

export function mergeMessages(current: Message[], incoming: Message[]): Message[] {
  if (incoming.length === 0) return current;
  const byId = new Map(current.map((message) => [message.id, message]));
  for (const message of incoming) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

export function lastMessageId(messages: Message[]): number {
  return messages.length === 0 ? 0 : (messages[messages.length - 1]?.id ?? 0);
}

export function reduce(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "reset":
      return initialState;
    case "messages": {
      const messages = mergeMessages(state.messages, action.items);
      const doneRuns = new Set(action.items.map((m) => m.run_id).filter((id): id is string => Boolean(id)));
      const doneSeats = new Set(
        action.items.filter((m) => m.author_kind === "agent" && !m.run_id).map((m) => m.author),
      );
      const typing = state.typing.filter((t) => !doneRuns.has(t.runId) && !doneSeats.has(t.seat));
      return { ...state, messages, typing, loaded: state.loaded || Boolean(action.loaded) };
    }
    case "history":
      // A page of older messages (or the first page): it also says where the page before it starts.
      return {
        ...state,
        messages: mergeMessages(state.messages, action.items),
        earlier: action.earlier,
        loaded: true,
      };
    case "listening":
      return {
        ...state,
        orders: Object.fromEntries(action.orders.map((order) => [order.id, order])),
        requests: Object.fromEntries(action.requests.map((request) => [request.id, request])),
      };
    case "order":
      return { ...state, orders: { ...state.orders, [action.order.id]: action.order } };
    case "example":
      return { ...state, examples: { ...state.examples, [action.messageId]: action.marked } };
    case "pending":
      return { ...state, pending: [...state.pending, action.pending] };
    case "delivered":
      return {
        ...state,
        pending: state.pending.filter((p) => p.key !== action.key),
        messages: mergeMessages(state.messages, [action.message]),
        delivered: [...state.delivered, action.message.id],
      };
    case "sendFailed":
      return {
        ...state,
        pending: state.pending.map((p) =>
          p.key === action.key ? { ...p, error: { message: action.message, hint: action.hint } } : p,
        ),
      };
    case "dropPending":
      return { ...state, pending: state.pending.filter((p) => p.key !== action.key) };
    case "reply": {
      const { run_id: runId, seat, text } = action.chunk;
      const existing = state.typing.find((t) => t.runId === runId);
      const typing = existing
        ? state.typing.map((t) => (t.runId === runId ? { ...t, text: t.text + text, updatedAt: action.at } : t))
        : [...state.typing, { runId, seat, text, updatedAt: action.at }];
      return { ...state, typing };
    }
    case "dropTyping":
      return { ...state, typing: state.typing.filter((t) => t.runId !== action.runId) };
    case "pruneTyping": {
      const working = new Set((state.header?.now ?? []).map((w) => w.seat));
      const typing = state.typing.filter(
        (t) => working.has(t.seat) || action.now - t.updatedAt < action.quietMs,
      );
      return typing.length === state.typing.length ? state : { ...state, typing };
    }
    case "header":
      return { ...state, header: action.header };
    case "cards":
      return { ...state, cards: Object.fromEntries(action.cards.map((card) => [card.id, card])) };
    case "card":
      return { ...state, cards: { ...state.cards, [action.card.id]: action.card } };
    case "notice":
      return { ...state, notices: [...state.notices, action.notice] };
    case "dropNotice":
      return { ...state, notices: state.notices.filter((n) => n.key !== action.key) };
    case "live":
      return state.live === action.live ? state : { ...state, live: action.live };
    case "changed":
      return { ...state, changes: state.changes + 1 };
  }
}
