/** Alerts on this device (INT-7), explained plainly, and the person's own alert and brief settings. */
import { useEffect, useState } from "react";
import { Bell, BellOff } from "lucide-react";
import { ErrorNote } from "../components/common";
import { alertState, turnOffAlerts, turnOnAlerts, type AlertState } from "../lib/push";
import { settingsWords } from "../strings.settings";
import { Pill } from "../ui/Status";
import { PersonalSettings } from "./PersonalSettings";

export function NotificationsSection(): JSX.Element {
  const words = settingsWords.notifications;
  const [state, setState] = useState<AlertState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let current = true;
    alertState()
      .then((value) => {
        if (current) setState(value);
      })
      .catch(() => {
        if (current) setState("unavailable");
      });
    return () => {
      current = false;
    };
  }, []);

  const change = (work: () => Promise<AlertState>): void => {
    setBusy(true);
    setError(null);
    work()
      .then(setState)
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(false));
  };

  const line =
    state === "on" ? words.on : state === "off" ? words.off : state === "blocked" ? words.blocked : state === "unavailable" ? words.unavailable : words.checking;

  return (
    <>
      <section className="card settings-card" aria-labelledby="alerts-title" aria-busy={state === null}>
        <div className="alerts-device">
          <span className={`alerts-icon ${state === "on" ? "on" : ""}`} aria-hidden="true">
            {state === "on" ? <Bell size={20} /> : <BellOff size={20} />}
          </span>
          <div className="alerts-text">
            <h3 id="alerts-title">
              {words.title}{" "}
              {state === "on" ? (
                <Pill tone="success">{settingsWords.common.on}</Pill>
              ) : state === "off" ? (
                <Pill tone="neutral">{settingsWords.common.off}</Pill>
              ) : null}
            </h3>
            <p className="quiet">{words.body}</p>
            <p role="status" className={state === "blocked" ? "alerts-state warn" : "alerts-state"}>
              {line}
            </p>
            <ErrorNote error={error} />
            {state === "off" || state === "on" ? (
              <button
                type="button"
                className={state === "off" ? "button primary" : "button"}
                disabled={busy}
                onClick={() => change(state === "off" ? turnOnAlerts : turnOffAlerts)}
              >
                {busy ? words.working : state === "off" ? words.turnOn : words.turnOff}
              </button>
            ) : null}
          </div>
        </div>
      </section>

      <section className="card settings-card" aria-labelledby="alert-rules-title">
        <div className="settings-card-head">
          <h3 id="alert-rules-title">{words.rules}</h3>
        </div>
        <PersonalSettings
          label={words.rules}
          only={["alerts.level", "alerts.grace", "alerts.max_per_day", "brief.time", "brief.away_after", "agenda.days"]}
        />
      </section>
    </>
  );
}
