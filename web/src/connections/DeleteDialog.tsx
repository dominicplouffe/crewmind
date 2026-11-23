/** Deleting a connection (CON-1): first every project that uses it, then the choice. */
import { useState } from "react";
import { get, post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { Modal } from "../components/Modal";
import { useLoad } from "../lib/useLoad";
import { connectionWords as words } from "../strings.connections";
import { Skeleton } from "../ui/Skeleton";

interface Props {
  item: Schemas["ConnectionView"];
  onClose(): void;
  onDone(): void;
}

export function DeleteDialog({ item, onClose, onDone }: Props): JSX.Element {
  const detail = useLoad(() => get("/v1/connections/show", { connection: item.id }), [item.id]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const used = detail.data?.used_in ?? [];
  const hidden = detail.data?.hidden_uses ?? 0;
  const remove = (): void => {
    setBusy(true);
    setError(null);
    post("/v1/connections/delete", { connection: item.id })
      .then(onDone)
      .catch((reason: unknown) => {
        setError(reason);
        setBusy(false);
      });
  };
  return (
    <Modal title={words.deleteTitle(item.name)} testId="delete-connection" onClose={onClose}>
      {detail.loading && !detail.data ? <Skeleton lines={2} /> : null}
      <ErrorNote error={detail.error} />
      {detail.data ? (
        used.length > 0 || hidden > 0 ? (
          <>
            <p>{words.deleteUsed}</p>
            <ul className="delete-uses" data-testid="delete-uses">
              {used.map((use) => (
                <li key={use.project_id}>{use.project_name}</li>
              ))}
            </ul>
            {hidden > 0 ? <p className="quiet">{words.deleteHidden(hidden)}</p> : null}
          </>
        ) : (
          <p>{words.deleteUnused}</p>
        )
      ) : null}
      {item.kind === "secret" ? <p className="quiet">{words.deleteValue}</p> : null}
      <ErrorNote error={error} />
      <div className="modal-actions">
        <button type="button" className="button" onClick={onClose} disabled={busy} autoFocus>
          {words.keep}
        </button>
        <button type="button" className="button danger" onClick={remove} disabled={busy || !detail.data}>
          {words.deleteYes}
        </button>
      </div>
    </Modal>
  );
}
