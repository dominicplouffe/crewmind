/**
 * The provider behind every "needs you" count (HUM-10, CHAT-18). It loads the desk once for the
 * whole app, reloads when a project reports a change, when the tab comes back into view, and at a
 * steady pace while visible (the desk spans projects; no single live stream covers it).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { get } from "../api/client";
import { useAuth } from "../auth";
import { t } from "../strings";
import { countFor, summarize, titled, type DeskEntry, type NeedsSummary } from "./summary";

/** How often the desk is asked again while the page is visible. A display refresh, not a rule. */
const REFRESH_EVERY_MS = 20000;

export interface NeedsYouValue extends NeedsSummary {
  loaded: boolean;
  error: unknown;
  reload(): void;
  countFor(projectId: string): number;
  forProject(projectId: string): DeskEntry[];
}

const NeedsYouContext = createContext<NeedsYouValue | null>(null);

export function NeedsYouProvider({ children }: { children: ReactNode }): JSX.Element {
  const { person } = useAuth();
  const [entries, setEntries] = useState<DeskEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  const signedIn = Boolean(person);

  useEffect(() => {
    if (!signedIn) return;
    let current = true;
    get("/v1/desk/show")
      .then((desk) => {
        if (!current) return;
        setEntries(desk.waiting);
        setError(null);
        setLoaded(true);
      })
      .catch((reason: unknown) => {
        if (current) setError(reason);
      });
    return () => {
      current = false;
    };
  }, [signedIn, tick]);

  useEffect(() => {
    if (!signedIn) return;
    const again = (): void => {
      if (document.visibilityState === "visible") reload();
    };
    const timer = window.setInterval(again, REFRESH_EVERY_MS);
    document.addEventListener("visibilitychange", again);
    window.addEventListener("focus", again);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", again);
      window.removeEventListener("focus", again);
    };
  }, [signedIn, reload]);

  const value = useMemo<NeedsYouValue>(() => {
    const summary = summarize(entries);
    return {
      ...summary,
      loaded,
      error,
      reload,
      countFor: (projectId) => countFor(summary, projectId),
      forProject: (projectId) => summary.byProject.get(projectId) ?? [],
    };
  }, [entries, loaded, error, reload]);

  // The installed app's icon shows the same count, where the browser supports it.
  useEffect(() => {
    const nav = navigator as Navigator & { setAppBadge?(count: number): Promise<void>; clearAppBadge?(): Promise<void> };
    if (!loaded) return;
    if (value.count > 0) nav.setAppBadge?.(value.count).catch(() => undefined);
    else nav.clearAppBadge?.().catch(() => undefined);
  }, [loaded, value.count]);

  return <NeedsYouContext.Provider value={value}>{children}</NeedsYouContext.Provider>;
}

export function useNeedsYou(): NeedsYouValue {
  const value = useContext(NeedsYouContext);
  if (!value) throw new Error("useNeedsYou needs a NeedsYouProvider");
  return value;
}

/** Sets the page title, with the needs-you count in front of it. */
export function usePageTitle(base: string): void {
  const { count } = useNeedsYou();
  useEffect(() => {
    document.title = titled(base === t.app.name ? base : `${base} · ${t.app.name}`, count);
  }, [base, count]);
  useEffect(
    () => () => {
      document.title = t.app.name;
    },
    [],
  );
}
