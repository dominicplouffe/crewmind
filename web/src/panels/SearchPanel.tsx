/** Search across messages and files (CHAT-14), with a jump to each hit. */
import { FileText, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { get, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { Empty, Loading } from "./kit";
import { snippet } from "../chat/MessageItem";
import { formatDateTime } from "../lib/format";
import { t } from "../strings";
import { Avatar } from "../ui/Avatar";
import { AgentAvatar, useAgentName } from "../crew/names";

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
  const nameOf = useAgentName();

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
          <input
            id="search-query"
            type="search"
            value={query}
            autoFocus
            placeholder={t.search.placeholder}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" className="button primary" disabled={busy}>
            {t.search.submit}
          </button>
        </div>
      </form>
      <ErrorNote error={error} />
      {busy ? <Loading label={t.search.busy} /> : null}
      {!hits && !busy ? <Empty icon={Search} title={t.search.startTitle} next={t.search.startNext} /> : null}
      {hits ? (
        <div role="status" aria-live="polite">
          <p className="quiet search-count">{t.search.count(hits.messages.length, hits.artifacts.length)}</p>
        </div>
      ) : null}
      {hits && hits.messages.length > 0 ? (
        <section aria-label={t.search.messages}>
          <h3 className="group-title">{t.search.messages}</h3>
          <ul className="rows plain">
            {hits.messages.map((message) => (
              <li key={message.id}>
                {message.author_kind === "agent" ? (
                  <AgentAvatar seat={message.author} size="sm" />
                ) : (
                  <Avatar name={message.author} kind={message.author_kind === "person" ? "person" : "agent"} size="sm" />
                )}
                <div className="row-main">
                  <button type="button" className="row-title" onClick={() => onJump(message.id)}>
                    {t.search.jump(
                      message.author_kind === "agent" ? nameOf(message.author).name : message.author,
                      formatDateTime(message.at),
                    )}
                  </button>
                  <p className="search-hit-text">{snippet(message.body)}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {hits && hits.artifacts.length > 0 ? (
        <section aria-label={t.search.files}>
          <h3 className="group-title">{t.search.files}</h3>
          <ul className="rows plain">
            {hits.artifacts.map((name) => (
              <li key={name} className="file-row">
                <span className="row-icon" aria-hidden="true">
                  <FileText size={18} />
                </span>
                <div className="row-main">
                  <button type="button" className="row-title" onClick={() => onFile(name)}>
                    {name}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
