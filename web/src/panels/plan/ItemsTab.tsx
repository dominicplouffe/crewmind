/** Decision items: everything filed for the chairman in this project, open or settled, with its history on demand. */
import { Scale } from "lucide-react";
import { useState } from "react";
import { get } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { Empty, Loading } from "../kit";
import { ItemCard } from "../../desk/ItemCard";
import type { Item } from "../../desk/logic";
import { formatDateTime } from "../../lib/format";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import type { TabProps } from "../memory/parts";

function History({ item }: { item: Item }): JSX.Element {
  const words = t.decisions.items;
  const detail = useLoad(() => get("/v1/items/show", { project_id: item.project_id, item_id: item.id }), [item]);
  if (!detail.data) return detail.error ? <ErrorNote error={detail.error} /> : <Loading />;
  if (detail.data.history.length === 0) return <p className="quiet">{words.noHistory}</p>;
  return (
    <ol className="plain item-history" aria-label={words.historyLabel(item.title)} data-testid="item-history">
      {detail.data.history.map((line, index) => (
        <li key={index}>
          <span className="quiet">{formatDateTime(line.at)}</span> {words.historyLine(line.actor_kind, line.what)}
          {line.state ? <span className="quiet"> ({words.historyState(line.state)})</span> : null}
        </li>
      ))}
    </ol>
  );
}

export function ItemsTab({ projectId, changes, onChanged }: TabProps): JSX.Element {
  const words = t.decisions.items;
  const [openOnly, setOpenOnly] = useState(true);
  const [history, setHistory] = useState<number | null>(null);
  const list = useLoad(
    () => get("/v1/items/list", { project_id: projectId, open_only: openOnly }),
    [projectId, changes, openOnly],
  );
  const items = list.data?.items ?? [];

  return (
    <>
      <div className="row wrap board-bar" role="group" aria-label={words.show}>
        <span className="quiet">{words.show}</span>
        <span className="segmented">
          <button type="button" aria-pressed={openOnly} onClick={() => setOpenOnly(true)}>
            {words.open}
          </button>
          <button type="button" aria-pressed={!openOnly} onClick={() => setOpenOnly(false)}>
            {words.all}
          </button>
        </span>
      </div>
      <ErrorNote error={list.error} />
      {!list.data && !list.error ? <Loading /> : null}
      {list.data && items.length === 0 ? (
        <Empty
          icon={Scale}
          title={openOnly ? words.emptyOpenTitle : words.emptyAllTitle}
          next={openOnly ? words.emptyOpenNext : words.emptyAllNext}
        />
      ) : null}
      <ul className="records plain item-list" aria-label={words.listLabel}>
        {items.map((item) => (
          <li key={item.id} data-testid="item">
            <ItemCard
              item={item}
              onChanged={() => {
                list.reload();
                onChanged();
              }}
            />
            <p className="row-meta item-dates">
              <span>{words.opened(formatDateTime(item.opened_at))}</span>
              {item.closed_at ? <span>{words.closed(formatDateTime(item.closed_at))}</span> : null}
              <button
                type="button"
                className="button small ghost"
                aria-expanded={history === item.id}
                onClick={() => setHistory(history === item.id ? null : item.id)}
              >
                {history === item.id ? words.hideHistory : words.history}
                <span className="visually-hidden"> {words.historyOf(item.title)}</span>
              </button>
            </p>
            {history === item.id ? <History item={item} /> : null}
          </li>
        ))}
      </ul>
    </>
  );
}
