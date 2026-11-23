/**
 * The person's unfinished drafting conversations, so they can go on with one or discard it
 * (FND-1, 7.19). Discarding asks once first: it cannot be undone.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";
import { get, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";

interface Draft {
  drafting_id: string;
  opening: string;
  quick: boolean;
  updated_at: string;
}

function DraftRow({ draft, onDiscarded }: { draft: Draft; onDiscarded: () => void }): JSX.Element {
  const words = t.founder.way;
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  function discard(): void {
    setBusy(true);
    setError(null);
    post("/v1/founder/discard", { drafting_id: draft.drafting_id })
      .then(onDiscarded)
      .catch((failure: unknown) => {
        setError(failure);
        setBusy(false);
      });
  }

  return (
    <li className="draft-row">
      <div className="draft-row-main">
        <p className="draft-opening">{draft.opening || words.noOpening}</p>
        <p className="draft-meta">
          {draft.quick ? <span className="badge">{words.quickTag}</span> : null}
          <span>{words.updated(formatDateTime(draft.updated_at))}</span>
        </p>
      </div>
      <div className="draft-row-actions">
        <Link to={`/draft/${draft.drafting_id}`} className="button small">
          {words.resume}
          <span className="visually-hidden"> {words.resumeOf(draft.opening)}</span>
        </Link>
        <button
          type="button"
          className="button small ghost icon-only"
          aria-label={words.discardOf(draft.opening)}
          aria-expanded={confirming}
          onClick={() => setConfirming(true)}
          disabled={busy}
        >
          <Trash2 size={16} aria-hidden="true" />
        </button>
      </div>
      <ErrorNote error={error} />
      {confirming ? (
        <div className="note note-warning draft-confirm" role="group" aria-label={words.discardYes}>
          <p className="note-title">{words.discardConfirm}</p>
          <div className="note-actions">
            <button type="button" className="button danger" onClick={discard} disabled={busy}>
              {words.discardYes}
            </button>
            <button type="button" className="button" onClick={() => setConfirming(false)} disabled={busy} autoFocus>
              {words.discardNo}
            </button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function Unfinished(): JSX.Element | null {
  const words = t.founder.way;
  const draftings = useLoad(() => get("/v1/founder/list"), []);
  const open = (draftings.data?.items ?? []).filter((item) => item.state === "drafting");
  if (draftings.error) return <ErrorNote error={draftings.error} />;
  if (open.length === 0) return null;
  return (
    <section aria-labelledby="unfinished-title" data-testid="unfinished">
      <h2 id="unfinished-title">{words.unfinishedTitle}</h2>
      <ul className="draft-list" aria-label={words.unfinishedList}>
        {open.map((item) => (
          <DraftRow key={item.drafting_id} draft={item} onDiscarded={draftings.reload} />
        ))}
      </ul>
    </section>
  );
}
