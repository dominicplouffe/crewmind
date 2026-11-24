/**
 * Starting a project when some of the crew could not work yet (CON-5, PRJ-1). Lists what is
 * missing and who would wait for it. The chairman says a need is added (under any names, and
 * nothing second-guesses them), or starts without it: exactly those agents wait, and go to
 * work by themselves once it is added.
 */
import { useState } from "react";
import type { Schemas } from "../api/client";
import { Modal } from "../components/Modal";
import { startDialog as words } from "../strings.shell";

interface Props {
  waiting: Schemas["BlockerItem"][];
  onStartWithout(): Promise<void>;
  /** The chairman says what a need asks for is added, under any names (CON-5). */
  onMarkDone?(need: Schemas["NeedRef"]): Promise<void>;
  /** Opens the project's connections, where each missing one is added in place. */
  onAddNow?(): void;
  onClose(): void;
}

export function StartDialog({ waiting, onStartWithout, onMarkDone, onAddNow, onClose }: Props): JSX.Element {
  const [busy, setBusy] = useState(false);
  const seats = new Set(waiting.flatMap((item) => item.seats));
  return (
    <Modal title={words.title} testId="start-dialog" onClose={onClose}>
      <p className="quiet">{words.lead(seats.size)}</p>
      <ul className="start-waiting" data-testid="start-waiting">
        {waiting.map((item) => (
          <li key={item.text}>
            <span className="start-waiting-what">{item.text}</span>
            {item.seats.length > 0 ? <span className="start-waiting-who">{words.who(item.seats)}</span> : null}
            {item.need && onMarkDone ? (
              <button
                type="button"
                className="button small"
                disabled={busy}
                aria-label={words.markDoneFor(item.need.name)}
                onClick={() => {
                  const need = item.need;
                  if (!need) return;
                  setBusy(true);
                  void onMarkDone(need).finally(() => setBusy(false));
                }}
              >
                {words.markDone}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="quiet">{words.after}</p>
      <div className="modal-actions">
        <button type="button" className="button" onClick={onClose} disabled={busy}>
          {words.notNow}
        </button>
        {onAddNow ? (
          <button type="button" className="button" onClick={onAddNow} disabled={busy}>
            {words.addNow}
          </button>
        ) : null}
        <button
          type="button"
          className="button primary"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            void onStartWithout().finally(() => setBusy(false));
          }}
        >
          {busy ? words.starting : words.startWithout}
        </button>
      </div>
    </Modal>
  );
}
