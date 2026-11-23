/** Sets a waiting item aside for a while. It comes back by itself, and never later than its deadline. */
import { AlarmClock } from "lucide-react";
import { useState } from "react";
import { post } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { t } from "../strings";
import { snoozeLatest, snoozePresets, type Item } from "./logic";

export function Snooze({ item, onDone }: { item: Item; onDone(): void }): JSX.Element {
  const words = t.decisions.snooze;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const now = new Date();
  const presets = snoozePresets(now, item.deadline);
  const allowed = presets.filter((preset) => preset.allowed).length;

  const snooze = async (until: Date): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await post("/v1/items/snooze", { project_id: item.project_id, item_id: item.id, until: until.toISOString() });
      onDone();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="snooze">
      <div className="row wrap snooze-row" role="group" aria-label={words.label(item.title)}>
        <span className="quiet snooze-lead">
          <AlarmClock size={14} aria-hidden="true" />
          {words.lead}
        </span>
        {presets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className="button small ghost"
            disabled={busy || !preset.allowed}
            title={formatDateTime(preset.until.toISOString())}
            onClick={() => void snooze(preset.until)}
          >
            {words.presets[preset.id]}
          </button>
        ))}
      </div>
      {allowed === 0 ? (
        <p className="quiet">{words.tooLate}</p>
      ) : allowed < presets.length ? (
        <p className="quiet">{words.someTooLate(formatDateTime(snoozeLatest(now, item.deadline).toISOString()))}</p>
      ) : null}
      <ErrorNote error={error} />
    </div>
  );
}
