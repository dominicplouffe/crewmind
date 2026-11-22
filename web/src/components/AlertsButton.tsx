/** The "turn on alerts" control. Hidden when the server or the browser cannot do push. */
import { useEffect, useState } from "react";
import { alertState, turnOffAlerts, turnOnAlerts, type AlertState } from "../lib/push";
import { t } from "../strings";
import { ErrorNote } from "./common";

export function AlertsButton(): JSX.Element | null {
  const [state, setState] = useState<AlertState>("unavailable");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [explain, setExplain] = useState(false);

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

  if (state === "unavailable") return null;

  const change = async (): Promise<void> => {
    if (state === "blocked") {
      setExplain(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = state === "on" ? await turnOffAlerts() : await turnOnAlerts();
      setState(next);
      setExplain(next === "blocked");
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="alerts">
      <button type="button" className="button" onClick={() => void change()} disabled={busy}>
        {state === "on" ? t.alerts.turnOff : t.alerts.turnOn}
      </button>
      {explain ? (
        <span className="quiet" role="status">
          {t.alerts.blocked}
        </span>
      ) : null}
      <ErrorNote error={error} />
    </span>
  );
}
