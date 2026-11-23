/**
 * Loads one drafting conversation, keeps it live over its stream, and reloads it every few seconds
 * while the stream is down (FND-1). Every action sends one operation and shows what came back.
 */
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { get, post, type Schemas } from "../api/client";
import { followEvents } from "../api/sse";
import { actionOf, draftingStreamUrl, initialConversation, lastLineId, reduceConversation, type ConversationState } from "./conversation";
import type { Drafting } from "./logic";

export type CreatedProject = Schemas["CreatedProject"];

/** How often the conversation is reloaded while the live stream is down. */
const POLL_EVERY_MS = 4000;

export interface DraftingActions {
  say(body: string): Promise<boolean>;
  answer(questionId: number, answer: string): Promise<boolean>;
  /** Sends a whole round of answers, in order. Resolves true when the server took them all. */
  answerAll(answers: { questionId: number; answer: string }[]): Promise<boolean>;
  acceptRest(): Promise<boolean>;
  create(): Promise<boolean>;
  /** Starts the created project. Resolves with its id when it started. */
  start(): Promise<string | null>;
}

export interface DraftingHook {
  state: ConversationState;
  /** Why the conversation could not be loaded at all. */
  loadError: unknown;
  /** The server's refusal of the last action. */
  error: unknown;
  busy: boolean;
  /** What `founder create` answered, kept while the page is open. */
  created: CreatedProject | null;
  actions: DraftingActions;
}

export function useDrafting(draftingId: string): DraftingHook {
  const [state, dispatch] = useReducer(reduceConversation, initialConversation);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [loadError, setLoadError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<CreatedProject | null>(null);

  const reload = useCallback(async (): Promise<Drafting | null> => {
    try {
      const view = await get("/v1/founder/show", { drafting_id: draftingId });
      dispatch({ type: "view", view });
      return view;
    } catch {
      // The page keeps what it has; the next change or poll asks again.
      return null;
    }
  }, [draftingId]);

  useEffect(() => {
    let closed = false;
    let stream: { close(): void } | null = null;
    dispatch({ type: "reset" });
    setLoadError(null);
    setError(null);
    setCreated(null);
    get("/v1/founder/show", { drafting_id: draftingId })
      .then((view) => {
        if (closed) return;
        dispatch({ type: "view", view });
        stream = followEvents(() => draftingStreamUrl(draftingId, lastLineId(stateRef.current.view)), {
          onEvent: (event) => {
            const action = actionOf(event);
            if (action) dispatch(action);
          },
          onStatus: (live) => dispatch({ type: "live", live }),
          // A 401 on the stream means the session ended: asking who is signed in routes to sign-in.
          onSignedOut: () => void get("/v1/auth/whoami").catch(() => undefined),
        });
      })
      .catch((reason: unknown) => {
        if (!closed) setLoadError(reason);
      });
    return () => {
      closed = true;
      stream?.close();
    };
  }, [draftingId]);

  // The stream said the conversation changed: ask for the questions, ledger, draft and readiness again.
  useEffect(() => {
    if (state.stale > 0) void reload();
  }, [state.stale, reload]);

  // Polling fallback while the stream is down.
  const loaded = state.view !== null;
  useEffect(() => {
    if (state.live || !loaded) return;
    const timer = window.setInterval(() => void reload(), POLL_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [state.live, loaded, reload]);

  const run = useCallback(async <T>(work: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    setError(null);
    try {
      return await work();
    } catch (reason) {
      setError(reason);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const actions = useMemo<DraftingActions>(() => {
    const show = async (work: () => Promise<Drafting>): Promise<boolean> => {
      const view = await run(work);
      if (view) dispatch({ type: "view", view });
      return view !== null;
    };
    return {
      say: (body) => show(() => post("/v1/founder/say", { drafting_id: draftingId, body })),
      answer: (questionId, answer) =>
        show(() => post("/v1/founder/answer", { drafting_id: draftingId, question_id: questionId, answer })),
      answerAll: (answers) =>
        show(async () => {
          // The Founder takes its turn after the last answer of the round (FND-4).
          let view: Drafting | null = null;
          for (const { questionId, answer } of answers) {
            view = await post("/v1/founder/answer", { drafting_id: draftingId, question_id: questionId, answer });
          }
          if (!view) throw new Error("There was nothing to send.");
          return view;
        }),
      acceptRest: () => show(() => post("/v1/founder/accept_rest", { drafting_id: draftingId })),
      async create() {
        const project = await run(() => post("/v1/founder/create", { drafting_id: draftingId, start: false }));
        if (!project) return false;
        setCreated(project);
        await reload();
        return true;
      },
      async start() {
        const projectId = created?.project_id ?? stateRef.current.view?.project_id;
        if (!projectId) return null;
        const status = await run(() => post("/v1/projects/start", { project_id: projectId }));
        return status ? projectId : null;
      },
    };
  }, [created, draftingId, reload, run]);

  return { state, loadError, error, busy, created, actions };
}
