/**
 * Whether this install is ready for someone to start a project by talking with the Founder
 * (LLM-14, FND-2): a model key exists, and `founder.credential` names an active one.
 *
 * Members cannot read install settings, so for them the Founder is treated as ready: they are not
 * blocked, and the drafting page explains a failure if it comes. Every mounted copy of the hook
 * reloads when `refreshSetupStatus()` is called (after a key is added or the Founder is set).
 */
import { useCallback, useEffect, useState } from "react";
import { get, type Schemas } from "../api/client";
import { useAuth } from "../auth";

type Credential = Schemas["CredentialItem"];

export interface SetupStatus {
  loading: boolean;
  isAdmin: boolean;
  hasModelKey: boolean;
  founderReady: boolean;
  reload(): void;
}

/** The setting's stored word for "no credential chosen". */
const NONE = "none";

const listeners = new Set<() => void>();

/** Tells every mounted `useSetupStatus` to ask the server again. */
export function refreshSetupStatus(): void {
  for (const listener of listeners) listener();
}

/** Model keys that can be used: active ones. */
export function usableModelKeys(items: Credential[]): Credential[] {
  return items.filter((item) => item.kind === "model" && item.state === "active");
}

/** The Founder is ready when its credential names a usable key. */
export function founderReadyWith(credentialName: unknown, items: Credential[]): boolean {
  if (typeof credentialName !== "string" || credentialName === "" || credentialName === NONE) return false;
  return usableModelKeys(items).some((item) => item.name === credentialName);
}

export function useSetupStatus(): SetupStatus {
  const { person } = useAuth();
  const isAdmin = person?.role === "admin";
  const [tick, setTick] = useState(0);
  const [state, setState] = useState({ loading: true, hasModelKey: false, founderReady: true });

  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    listeners.add(reload);
    return () => {
      listeners.delete(reload);
    };
  }, [reload]);

  useEffect(() => {
    if (!person) return;
    let current = true;
    setState((previous) => ({ ...previous, loading: true }));
    const credentials = get("/v1/credentials/list")
      .then((list) => list.items)
      .catch(() => null);
    const install = isAdmin ? get("/v1/settings/show_install").catch(() => null) : Promise.resolve(null);
    void Promise.all([credentials, install]).then(([items, settings]) => {
      if (!current) return;
      const keys = items ?? [];
      const credential = settings?.items.find((item) => item.name === "founder.credential")?.value;
      setState({
        loading: false,
        // When the list can't be read, don't send the person through setup again.
        hasModelKey: items === null ? true : usableModelKeys(keys).length > 0,
        // Unknown (a member, or the settings could not be read) counts as ready.
        founderReady: settings === null || items === null ? true : founderReadyWith(credential, keys),
      });
    });
    return () => {
      current = false;
    };
  }, [person, isAdmin, tick]);

  // Coming back to the tab after fixing setup elsewhere: ask again.
  const needsLook = !state.loading && (!state.founderReady || !state.hasModelKey);
  useEffect(() => {
    if (!needsLook) return;
    const onVisible = (): void => {
      if (document.visibilityState === "visible") reload();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [needsLook, reload]);

  return { ...state, loading: person === undefined || state.loading, isAdmin, reload };
}
