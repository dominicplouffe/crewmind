/** Browser alerts: whether they are on, and turning them on or off. Hidden where push cannot work. */
import { useCallback, useEffect, useState } from "react";
import { alertState, turnOffAlerts, turnOnAlerts, type AlertState } from "../lib/push";

export function useAlerts(): { state: AlertState; busy: boolean; error: unknown; toggle(): Promise<void> } {
  const [state, setState] = useState<AlertState>("unavailable");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let current = true;
    alertState()
      .then((value) => {
        if (current) setState(value);
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, []);

  const toggle = useCallback(async () => {
    if (state === "blocked" || state === "unavailable") return;
    setBusy(true);
    setError(null);
    try {
      setState(state === "on" ? await turnOffAlerts() : await turnOnAlerts());
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }, [state]);

  return { state, busy, error, toggle };
}
