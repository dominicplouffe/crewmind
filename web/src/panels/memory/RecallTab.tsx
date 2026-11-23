/** Recalled memory: facts by scope, search, add, edit, pin and forget; and the person's own preferences. */
import { Brain, Heart } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { get, post } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { Empty, Loading } from "../kit";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { EntryList } from "./EntryList";
import { ServerNote, TextForm, useAct, type TabProps } from "./parts";

export function RecallTab({ projectId, changes, onChanged }: TabProps): JSX.Element {
  const [scope, setScope] = useState("");
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId]);
  const entries = useLoad(
    () =>
      query
        ? get("/v1/memory/search", { project_id: projectId, query })
        : get("/v1/memory/list", { project_id: projectId, scope: scope || undefined }),
    [projectId, scope, query, changes],
  );
  const act = useAct(() => {
    entries.reload();
    onChanged();
  });
  const scopeId = useId();
  const searchId = useId();
  const words = t.memory.recall;
  const items = entries.data?.items ?? [];

  const search = (event: FormEvent): void => {
    event.preventDefault();
    setNote(null);
    setQuery(typed.trim());
  };

  return (
    <>
      <form className="row wrap search-form" role="search" onSubmit={search}>
        <label htmlFor={searchId} className="visually-hidden">
          {words.searchLabel}
        </label>
        <input
          id={searchId}
          type="search"
          value={typed}
          placeholder={words.searchLabel}
          onChange={(event) => setTyped(event.target.value)}
        />
        <button type="submit" className="button small">
          {words.search}
        </button>
        {query ? (
          <button
            type="button"
            className="button small"
            onClick={() => {
              setTyped("");
              setQuery("");
            }}
          >
            {words.clearSearch}
          </button>
        ) : null}
      </form>
      {query ? (
        entries.data && !entries.loading && !entries.error ? (
          <p role="status" data-testid="memory-found">
            {words.found(items.length, query)}
          </p>
        ) : null
      ) : (
        <div className="field">
          <label htmlFor={scopeId}>{words.scope}</label>
          <select id={scopeId} value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="">{words.allScopes}</option>
            <option value="project">{words.project}</option>
            {(roster.data?.teams ?? []).map((team) => (
              <option key={`team ${team}`} value={`team ${team}`}>
                {words.team(team)}
              </option>
            ))}
            {(roster.data?.seats ?? []).map((seat) => (
              <option key={`agent ${seat.name}`} value={`agent ${seat.name}`}>
                {words.agent(seat.display_name || seat.name)}
              </option>
            ))}
          </select>
        </div>
      )}
      <TextForm
        label={words.addLabel}
        submit={words.add}
        onSubmit={async (text) => {
          await post("/v1/memory/remember", { project_id: projectId, text, scope: scope || undefined });
          setNote(null);
          entries.reload();
          onChanged();
        }}
      />
      <ServerNote text={note} />
      <ErrorNote error={entries.error} />
      <ErrorNote error={act.error} />
      {entries.loading && !entries.data ? <Loading /> : null}
      {entries.data && items.length === 0 && !query ? <Empty icon={Brain} title={words.emptyTitle} next={words.emptyNext} /> : null}
      <EntryList
        label={words.listLabel}
        items={items}
        busy={act.busy}
        showScope
        onEdit={async (entry, text) => {
          await post("/v1/memory/edit", { project_id: projectId, memory_id: entry.id, text });
          entries.reload();
          onChanged();
        }}
        onPin={(entry) =>
          void act
            .run(() => post("/v1/memory/pin", { project_id: projectId, memory_id: entry.id }))
            .then((worked) => setNote(worked ? words.pinned : null))
        }
        onForget={(entry) => void act.run(() => post("/v1/memory/forget", { project_id: projectId, memory_id: entry.id }))}
      />
    </>
  );
}

export function PreferencesTab(): JSX.Element {
  const preferences = useLoad(() => get("/v1/memory/preferences"), []);
  const act = useAct(preferences.reload);
  const words = t.memory.preferences;
  const items = preferences.data?.items ?? [];
  return (
    <>
      <p className="quiet">{words.intro}</p>
      <TextForm
        label={words.addLabel}
        submit={words.add}
        onSubmit={async (text) => {
          await post("/v1/memory/prefer", { text });
          preferences.reload();
        }}
      />
      <ErrorNote error={preferences.error} />
      <ErrorNote error={act.error} />
      {preferences.loading && !preferences.data ? <Loading /> : null}
      {preferences.data && items.length === 0 ? <Empty icon={Heart} title={words.emptyTitle} next={words.emptyNext} /> : null}
      <EntryList
        label={words.listLabel}
        items={items}
        busy={act.busy}
        onForget={(entry) => void act.run(() => post("/v1/memory/forget_preference", { memory_id: entry.id }))}
      />
    </>
  );
}
