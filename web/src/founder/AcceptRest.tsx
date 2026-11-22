/**
 * "Use your recommendations for the rest" (FND-15): asks first, and says that what is accepted
 * this way is recorded as an assumption, not as the person's answer.
 */
import { useState } from "react";
import { Modal } from "../components/Modal";
import { t } from "../strings";

interface Props {
  busy: boolean;
  /** Resolves true when the server took it. */
  onAccept(): Promise<boolean>;
}

export function AcceptRest({ busy, onAccept }: Props): JSX.Element {
  const words = t.founder.rest;
  const [asking, setAsking] = useState(false);
  return (
    <>
      <button type="button" className="button" disabled={busy} onClick={() => setAsking(true)}>
        {words.action}
      </button>
      {asking ? (
        <Modal title={words.title} testId="accept-rest" onClose={() => setAsking(false)}>
          <p>{words.explain}</p>
          <div className="row wrap">
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={() => {
                setAsking(false);
                void onAccept();
              }}
            >
              {words.confirm}
            </button>
            <button type="button" className="button" onClick={() => setAsking(false)}>
              {t.common.cancel}
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
