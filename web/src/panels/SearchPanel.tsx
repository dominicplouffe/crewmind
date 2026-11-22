/** Search across messages and files (CHAT-14), with a jump to each hit. */
import { useState, type FormEvent } from "react";
import { get, type Schemas } from "../api/client";
import { Empty, ErrorNote, Loading } from "../components/common";
import { snippet } from "../chat/MessageItem";
import { formatDateTime } from "../lib/format";
import { t } from "../strings";

interface Props {
  projectId: string;
  onJump(messageId: number): void;
  onFile(name: string): void;
}

export function SearchPanel({ projectId, onJump, onFile }: Props): JSX.Element {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Schemas["SearchHits"] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const search = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (query.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      setHits(await get("/v1/chat/search", { project_id: projectId, query }));
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <form role="search" className="search-form" onSubmit={(event) => void search(event)}>
        <label htmlFor="search-query">{t.search.label}</label>
        <div className="row">
          <input id="search-query" type="search" value={query} autoFocus onChange={(event) => setQuery(event.target.value)} />
          <button type="submit" className="button primary" disabled={busy}>
            {t.search.submit}
          </button>
        </div>
      </form>
      <ErrorNote error={error} />
      {busy ? <Loading label={t.search.busy} /> : null}
      {!hits && !busy ? <Empty title={t.search.startTitle} next={t.search.startNext} /> : null}
      {hits ? (
        <div role="status" aria-live="polite">
          <p className="quiet">{t.search.count(hits.messages.length, hits.artifacts.length)}</p>
        </div>
      ) : null}
      {hits && hits.messages.length > 0 ? (
        <section aria-label={t.search.messages}>
          <h3>{t.search.messages}</h3>
          <ul className="cards plain">
            {hits.messages.map((message) => (
              <li key={message.id} className="mini-card">
                <button type="button" className="link strong" onClick={() => onJump(message.id)}>
                  {t.search.jump(message.author, formatDateTime(message.at))}
                </button>
                <p>{snippet(message.body)}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {hits && hits.artifacts.length > 0 ? (
        <section aria-label={t.search.files}>
          <h3>{t.search.files}</h3>
          <ul className="plain">
            {hits.artifacts.map((name) => (
              <li key={name}>
                <button type="button" className="link" onClick={() => onFile(name)}>
                  {name}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
