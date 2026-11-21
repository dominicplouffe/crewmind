/** Loads a project's chat, keeps it live over the stream, and falls back to polling when the stream drops. */
import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { ApiError, get, post, type Message } from "../api/client";
import { openStream } from "../api/sse";
import { isCommand } from "../lib/autocomplete";
import { t } from "../strings";
import { initialState, lastMessageId, reduce, type ChatState } from "./state";

const REFRESH_DEBOUNCE_MS = 250;
const POLL_EVERY_MS = 4000;
const TYPING_QUIET_MS = 15000;
const PAGE_SIZE = 200;

export interface ChatActions {
  send(body: string, replyTo: number | null): Promise<void>;
  retry(key: string): void;
  dismissPending(key: string): void;
  dismissNotice(key: string): void;
  interrupt(): Promise<boolean>;
  acceptCard(cardId: number, edited?: string): Promise<void>;
  dismissCard(cardId: number): Promise<void>;
  projectAction(action: "start" | "hold" | "resume"): Promise<void>;
  refresh(): void;
  reportError(error: unknown): void;
}

let keyCounter = 0;
function nextKey(): string {
  keyCounter += 1;
  return `local-${keyCounter}`;
}

async function loadHistory(projectId: string, after: number): Promise<Message[]> {
  const items: Message[] = [];
  let cursor: string | undefined = after > 0 ? String(after) : undefined;
  for (;;) {
    const page = await get("/v1/chat/history", { project_id: projectId, limit: PAGE_SIZE, after: cursor });
    items.push(...page.items);
    if (!page.next) return items;
    cursor = page.next;
  }
}

export function useProjectChat(projectId: string): { state: ChatState; actions: ChatActions } {
  const [state, dispatch] = useReducer(reduce, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;
  const refreshTimer = useRef<number | null>(null);

  const reportError = useCallback((error: unknown) => {
    const api = error instanceof ApiError ? error : null;
    if (api?.status === 401) return;
    dispatch({
      type: "notice",
      notice: {
        key: nextKey(),
        kind: "error",
        title: t.errors.title,
        text: api?.message ?? t.errors.network,
        hint: api ? api.hint : t.errors.networkHint,
        data: null,
        afterMessage: lastMessageId(stateRef.current.messages),
      },
    });
  }, []);

  const refreshNow = useCallback(async () => {
    try {
      const [header, cards] = await Promise.all([
        get("/v1/chat/header", { project_id: projectId }),
        get("/v1/cards/list", { project_id: projectId }),
      ]);
      dispatch({ type: "header", header });
      dispatch({ type: "cards", cards: cards.items });
      dispatch({ type: "pruneTyping", now: Date.now(), quietMs: TYPING_QUIET_MS });
    } catch {
      // The header keeps its last value; the next change or poll retries.
    }
  }, [projectId]);

  const refresh = useCallback(() => {
    if (refreshTimer.current !== null) return;
    refreshTimer.current = window.setTimeout(() => {
      refreshTimer.current = null;
      dispatch({ type: "changed" });
      void refreshNow();
    }, REFRESH_DEBOUNCE_MS);
  }, [refreshNow]);

  useEffect(() => {
    let closed = false;
    let stream: ReturnType<typeof openStream> | null = null;
    dispatch({ type: "reset" });
    void refreshNow();
    loadHistory(projectId, 0)
      .then((items) => {
        if (closed) return;
        dispatch({ type: "messages", items, loaded: true });
        stream = openStream(
          projectId,
          { message: lastMessageId(items), event: null },
          {
            onMessage: (message) => dispatch({ type: "messages", items: [message] }),
            onChange: () => refresh(),
            onReply: (chunk) => dispatch({ type: "reply", chunk, at: Date.now() }),
            onStatus: (live) => dispatch({ type: "live", live }),
            // A 401 on the stream means the session ended: asking who is signed in routes to sign-in.
            onSignedOut: () => void get("/v1/auth/whoami").catch(() => undefined),
          },
        );
      })
      .catch((error: unknown) => {
        if (closed) return;
        dispatch({ type: "messages", items: [], loaded: true });
        reportError(error);
      });
    return () => {
      closed = true;
      stream?.close();
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current);
      refreshTimer.current = null;
    };
  }, [projectId, refresh, refreshNow, reportError]);

  // Polling fallback: while the stream is down, ask for new messages and the header on a timer.
  useEffect(() => {
    if (state.live || !state.loaded) return;
    const timer = window.setInterval(() => {
      loadHistory(projectId, lastMessageId(stateRef.current.messages))
        .then((items) => dispatch({ type: "messages", items }))
        .catch(() => undefined);
      void refreshNow();
      dispatch({ type: "changed" });
    }, POLL_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [projectId, refreshNow, state.live, state.loaded]);

  const deliver = useCallback(
    async (key: string, body: string, replyTo: number | null) => {
      try {
        if (isCommand(body)) {
          const outcome = await post("/v1/chat/command", { project_id: projectId, text: body.trim() });
          dispatch({ type: "dropPending", key });
          dispatch({
            type: "notice",
            notice: {
              key: nextKey(),
              kind: "result",
              title: t.chat.commandRan(outcome.command),
              text: "",
              hint: null,
              data: outcome.result as Record<string, unknown>,
              afterMessage: lastMessageId(stateRef.current.messages),
            },
          });
          refresh();
        } else {
          const message = await post("/v1/chat/send", { project_id: projectId, body, reply_to: replyTo });
          dispatch({ type: "delivered", key, message });
        }
      } catch (error) {
        const api = error instanceof ApiError ? error : null;
        dispatch({
          type: "sendFailed",
          key,
          message: api?.message ?? t.errors.network,
          hint: api ? api.hint : t.errors.networkHint,
        });
      }
    },
    [projectId, refresh],
  );

  const actions = useMemo<ChatActions>(
    () => ({
      async send(body, replyTo) {
        const key = nextKey();
        dispatch({ type: "pending", pending: { key, body, replyTo, error: null } });
        await deliver(key, body, replyTo);
      },
      retry(key) {
        const pending = stateRef.current.pending.find((p) => p.key === key);
        if (!pending) return;
        dispatch({ type: "dropPending", key });
        const fresh = nextKey();
        dispatch({ type: "pending", pending: { ...pending, key: fresh, error: null } });
        void deliver(fresh, pending.body, pending.replyTo);
      },
      dismissPending: (key) => dispatch({ type: "dropPending", key }),
      dismissNotice: (key) => dispatch({ type: "dropNotice", key }),
      async interrupt() {
        const typing = stateRef.current.typing;
        const target = typing[typing.length - 1];
        if (!target) return false;
        try {
          await post("/v1/runs/interrupt", { project_id: projectId, run_id: target.runId });
          dispatch({ type: "dropTyping", runId: target.runId });
          refresh();
        } catch (error) {
          reportError(error);
        }
        return true;
      },
      async acceptCard(cardId, edited) {
        try {
          const card = await post("/v1/cards/accept", { project_id: projectId, card_id: cardId, edited });
          dispatch({ type: "card", card });
          refresh();
        } catch (error) {
          reportError(error);
        }
      },
      async dismissCard(cardId) {
        try {
          const card = await post("/v1/cards/dismiss", { project_id: projectId, card_id: cardId });
          dispatch({ type: "card", card });
          refresh();
        } catch (error) {
          reportError(error);
        }
      },
      async projectAction(action) {
        try {
          await post(`/v1/projects/${action}`, { project_id: projectId });
          await refreshNow();
          dispatch({ type: "changed" });
        } catch (error) {
          reportError(error);
        }
      },
      refresh,
      reportError,
    }),
    [deliver, projectId, refresh, refreshNow, reportError],
  );

  return { state, actions };
}
