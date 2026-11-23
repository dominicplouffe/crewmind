/**
 * The client state of one drafting conversation and the reducer that updates it (FND-1). No rules:
 * it stores what `founder show` and the live stream send, and keeps them in step with each other.
 */
import type { SseEvent } from "../api/sse";
import type { Drafting, Line } from "./logic";

export interface ConversationState {
  /** The conversation as the server last described it, with any lines the stream added since. */
  view: Drafting | null;
  /** The Founder's words as they are produced, until the finished line is stored. */
  reply: string;
  /** What the Founder is doing right now, in its own plain words, while it works on a turn. */
  working: string;
  /** Whether the live stream is connected. */
  live: boolean;
  /** Whether the stream has dropped at least once since the page opened. */
  dropped: boolean;
  /** Goes up each time the stream says the conversation changed, so the page reloads it. */
  stale: number;
}

export const initialConversation: ConversationState = {
  view: null,
  reply: "",
  working: "",
  live: false,
  dropped: false,
  stale: 0,
};

export type ConversationAction =
  | { type: "reset" }
  | { type: "view"; view: Drafting }
  | { type: "line"; line: Line }
  | { type: "reply"; text: string }
  | { type: "working"; text: string }
  | { type: "changed" }
  | { type: "live"; live: boolean };

export function lastLineId(view: Drafting | null): number {
  return view?.lines.reduce((highest, line) => Math.max(highest, line.id), 0) ?? 0;
}

function isQuestion(line: Line): boolean {
  return (line.detail as { kind?: unknown } | null)?.kind === "question";
}

export function reduceConversation(state: ConversationState, action: ConversationAction): ConversationState {
  switch (action.type) {
    case "reset":
      return initialConversation;
    case "view": {
      // A reload can be older than the stream: keep the lines that arrived after the ones it holds.
      const newest = lastLineId(action.view);
      const later = (state.view?.drafting_id === action.view.drafting_id ? state.view.lines : []).filter(
        (line) => line.id > newest,
      );
      const view = later.length > 0 ? { ...action.view, lines: [...action.view.lines, ...later] } : action.view;
      const waiting = view.waiting_for === "the Founder";
      return { ...state, view, reply: waiting ? state.reply : "", working: waiting ? state.working : "" };
    }
    case "line": {
      if (!state.view) return state;
      // The Founder's finished words replace the words shown while it wrote them.
      const finished = action.line.author === "founder" && !isQuestion(action.line);
      const reply = finished ? "" : state.reply;
      const working = finished ? "" : state.working;
      if (state.view.lines.some((line) => line.id === action.line.id)) return { ...state, reply, working };
      const lines = [...state.view.lines, action.line].sort((a, b) => a.id - b.id);
      return { ...state, reply, working, view: { ...state.view, lines } };
    }
    case "reply":
      return { ...state, reply: state.reply + action.text };
    case "working":
      return { ...state, working: action.text };
    case "changed":
      return { ...state, stale: state.stale + 1 };
    case "live":
      return { ...state, live: action.live, dropped: state.dropped || !action.live };
    default:
      return state;
  }
}

/** Turns one event of the drafting stream into an action, or null when it carries nothing to store. */
export function actionOf(event: SseEvent): ConversationAction | null {
  let payload: unknown;
  try {
    payload = JSON.parse(event.data);
  } catch {
    return null;
  }
  if (typeof payload !== "object" || payload === null) return null;
  if (event.event === "line") {
    const line = payload as Line;
    return typeof line.id === "number" && typeof line.body === "string" ? { type: "line", line } : null;
  }
  if (event.event === "reply") {
    const text = (payload as { text?: unknown }).text;
    return typeof text === "string" ? { type: "reply", text } : null;
  }
  if (event.event === "working") {
    const text = (payload as { working?: unknown }).working;
    return typeof text === "string" ? { type: "working", text } : null;
  }
  return event.event === "state" ? { type: "changed" } : null;
}

export function draftingStreamUrl(draftingId: string, afterLine: number): string {
  return `/stream/v1/draftings/${encodeURIComponent(draftingId)}?after_line=${afterLine}`;
}
