/**
 * Starting a project when some of the squad could not work yet (CON-5, PRJ-1). Lists what is
 * missing and who would wait for it, and offers to start without it: exactly those agents
 * wait, and go to work by themselves once it is added.
 */
import { useState } from "react";
import type { Schemas } from "../api/client";
import { Modal } from "../components/Modal";
import { startDialog as words } from "../strings.shell";

interface Props {
  waiting: Schemas["BlockerItem"][];
  onStartWithout(): Promise<void>;
  /** Opens the project's connections, where each missing one is added in place. */
  onAddNow?(): void;
  onClose(): void;
}

export function StartDialog({ waiting, onStartWithout, onAddNow, onClose }: Props): JSX.Element {
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
