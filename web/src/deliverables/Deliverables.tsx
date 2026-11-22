/**
 * Deliverables as the hero (ART-3, CHAT-16): a gallery of what the crew made, each with a real
 * preview. A card opens the full file view (versions, downloads, compare) in a wide sheet.
 */
import { useEffect, useMemo, useState } from "react";
import { PackageOpen } from "lucide-react";
import { get } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { FileView } from "../panels/FileView";
import { deliverables as words } from "../strings.crew";
import { Sheet } from "../ui/Sheet";
import { DeliverableCard, madeBy, statusWord } from "./DeliverableCard";
import { FILTERS, SORTS, arrange, authorKind, countByFilter, defaultScope, type Filter, type Scope, type Sort } from "./logic";

interface Props {
  projectId: string;
  changes: number;
  /** A file to open first, for example from a link in the chat. */
  initialFile?: string;
}

function GallerySkeleton(): JSX.Element {
  return (
    <ul className="plain deliv-grid" aria-hidden="true">
      {[0, 1, 2, 3, 4, 5].map((index) => (
        <li key={index} className="deliv-card is-skeleton">
          <span className="skeleton deliv-skel-thumb" />
          <div className="deliv-body">
            <span className="skeleton line" />
            <span className="skeleton line" style={{ width: "55%" }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Deliverables({ projectId, changes, initialFile }: Props): JSX.Element {
  const { person } = useAuth();
  const list = useLoad(() => get("/v1/artifacts/list", { project_id: projectId }), [projectId, changes]);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, changes]);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("recent");
  const [chosenScope, setScope] = useState<Scope | null>(null);
  const [open, setOpen] = useState<string | null>(initialFile ?? null);

  useEffect(() => {
    if (initialFile) setOpen(initialFile);
  }, [initialFile]);

  const items = useMemo(() => list.data?.items ?? [], [list.data]);
  const seats = useMemo(() => new Set((roster.data?.seats ?? []).map((seat) => seat.name)), [roster.data]);
  const scope = chosenScope ?? defaultScope(items);
  const counts = useMemo(() => countByFilter(items, scope), [items, scope]);
  const shown = useMemo(() => arrange(items, filter, sort, scope), [items, filter, sort, scope]);
  const selected = items.find((item) => item.name === open);
  const anyFiles = items.length > 0;

  return (
    <section className="deliv" aria-labelledby="deliv-title" data-testid="deliverables">
      <header className="deliv-head">
        <div>
          <h2 id="deliv-title">{words.title}</h2>
          <p className="quiet">{words.intro}</p>
        </div>
        {anyFiles ? (
          <div className="deliv-controls">
            <label className="deliv-select">
              <span className="quiet">{words.scopeLabel}</span>
              <select value={scope} onChange={(event) => setScope(event.target.value as Scope)}>
                {(["delivered", "everything"] as const).map((value) => (
                  <option key={value} value={value}>
                    {words.scopes[value]}
                  </option>
                ))}
              </select>
            </label>
            <label className="deliv-select">
              <span className="quiet">{words.sortLabel}</span>
              <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
                {SORTS.map((value) => (
                  <option key={value} value={value}>
                    {words.sorts[value]}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : null}
      </header>

      {anyFiles ? (
        <div className="deliv-filters" role="group" aria-label={words.filtersLabel}>
          {FILTERS.filter((value) => value === "all" || value === filter || counts[value] > 0).map((value) => (
            <button
              key={value}
              type="button"
              className="chip"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {words.filters[value]}
              <span className="chip-count tabular">{counts[value]}</span>
            </button>
          ))}
          <span className="deliv-count quiet" aria-live="polite">
            {words.count(shown.length, counts.all)}
          </span>
        </div>
      ) : null}

      {list.error && !list.data ? (
        <div className="stack">
          <ErrorNote error={list.error} />
          <div>
            <button type="button" className="button small" onClick={list.reload}>
              {words.retry}
            </button>
          </div>
        </div>
      ) : null}
      {!list.data && !list.error ? (
        <>
          <span className="visually-hidden" role="status">
            {words.loading}
          </span>
          <GallerySkeleton />
        </>
      ) : null}

      {list.data && !anyFiles ? (
        <div className="empty deliv-empty">
          <span className="empty-icon">
            <PackageOpen size={22} aria-hidden="true" />
          </span>
          <p className="empty-title">{words.emptyTitle}</p>
          <p className="quiet">{words.emptyNext}</p>
        </div>
      ) : null}

      {anyFiles && shown.length === 0 ? (
        <div className="empty">
          <p className="empty-title">{words.noMatchTitle}</p>
          <p className="quiet">{words.noMatchNext}</p>
          <button
            type="button"
            className="button small empty-action"
            onClick={() => {
              setFilter("all");
              setScope("everything");
            }}
          >
            {words.showAll}
          </button>
        </div>
      ) : null}

      {shown.length > 0 ? (
        <ul className="plain deliv-grid">
          {shown.map((item) => (
            <li key={item.name}>
              <DeliverableCard
                projectId={projectId}
                item={item}
                author={authorKind(item, seats)}
                me={person?.name}
                onOpen={() => setOpen(item.name)}
              />
            </li>
          ))}
        </ul>
      ) : null}

      {open ? (
        <Sheet
          title={open}
          subtitle={
            selected
              ? `${words.sheetSubtitle(words.kinds[selected.kind] ?? selected.kind, statusWord(selected.status), words.versions(selected.versions))} · ${madeBy(selected, authorKind(selected, seats), person?.name)}`
              : undefined
          }
          size="xl"
          testId="deliverable-sheet"
          onClose={() => setOpen(null)}
        >
          <div className="deliv-sheet">
            <FileView projectId={projectId} name={open} artifact={selected} changes={changes} onBack={() => setOpen(null)} />
          </div>
        </Sheet>
      ) : null}
    </section>
  );
}
