/** The read-only panels: activity feed, budget, models. */
import { get, type Seat } from "../api/client";
import { Empty, ErrorNote, Loading } from "../components/common";
import { formatDateTime, formatNumber, percent } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { listeningLine } from "./memory/PinnedTab";

interface Props {
  projectId: string;
  /** Changes whenever the project changes, so the panel reloads. */
  changes: number;
}

async function loadFeed(projectId: string): Promise<Awaited<ReturnType<typeof get<"/v1/record/feed">>>["items"]> {
  const items = [];
  let after: string | undefined;
  for (;;) {
    const page = await get("/v1/record/feed", { project_id: projectId, after, limit: 200 });
    items.push(...page.items);
    if (!page.next) return items;
    after = page.next;
  }
}

export function FeedPanel({ projectId, changes }: Props): JSX.Element {
  const feed = useLoad(() => loadFeed(projectId), [projectId, changes]);
  const items = [...(feed.data ?? [])].reverse();
  return (
    <>
      <ErrorNote error={feed.error} />
      {feed.loading && !feed.data ? <Loading /> : null}
      {feed.data && items.length === 0 ? <Empty title={t.feed.emptyTitle} next={t.feed.emptyNext} /> : null}
      <ol className="feed plain" aria-label={t.feed.listLabel}>
        {items.map((item) => (
          <li key={item.id}>
            <time dateTime={item.at} className="quiet">
              {formatDateTime(item.at)}
            </time>
            <span>{item.text}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

export function BudgetPanel({ projectId, changes }: Props): JSX.Element {
  const budget = useLoad(() => get("/v1/budget/show", { project_id: projectId }), [projectId, changes]);
  const data = budget.data;
  return (
    <>
      <ErrorNote error={budget.error} />
      {budget.loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <p className="lead" id="budget-summary">
            {data.summary}
          </p>
          <progress max={100} value={percent(data.spent, data.wall)} aria-labelledby="budget-summary" />
          {data.at_wall ? (
            <p className="note note-error" role="status">
              {t.budget.atWall}
            </p>
          ) : null}
          <dl className="pairs">
            <div>
              <dt>{t.budget.used}</dt>
              <dd>{t.budget.tokens(formatNumber(data.spent))}</dd>
            </div>
            <div>
              <dt>{t.budget.remaining}</dt>
              <dd>{t.budget.tokens(formatNumber(data.remaining))}</dd>
            </div>
            <div>
              <dt>{t.budget.wall}</dt>
              <dd>{t.budget.tokens(formatNumber(data.wall))}</dd>
            </div>
            <div>
              <dt>{t.budget.warnAt}</dt>
              <dd>{t.budget.tokens(formatNumber(data.warn_at))}</dd>
            </div>
            <div>
              <dt>{t.budget.wrapupAt}</dt>
              <dd>{t.budget.tokens(formatNumber(data.wrapup_at))}</dd>
            </div>
          </dl>
          <h3>{t.budget.byKind}</h3>
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">{t.budget.kind}</th>
                <th scope="col" className="num">
                  {t.budget.tokensHead}
                </th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.by_kind).map(([kind, count]) => (
                <tr key={kind}>
                  <th scope="row">{t.budget.kinds[kind as keyof typeof t.budget.kinds] ?? kind.replace(/_/g, " ")}</th>
                  <td className="num">{formatNumber(Number(count))}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="quiet">{t.budget.cacheNote}</p>
        </>
      ) : null}
    </>
  );
}

export function ModelsPanel({ projectId, changes }: Props): JSX.Element {
  const models = useLoad(() => get("/v1/models/show", { project_id: projectId }), [projectId, changes]);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, changes]);
  const data = models.data;
  const agentOf = (name: string): Seat | undefined => roster.data?.seats.find((seat) => seat.name === name);
  return (
    <>
      <ErrorNote error={models.error} />
      {models.loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <p className="lead">{t.models.quality(data.quality)}</p>
          {data.seats.length === 0 ? <Empty title={t.models.emptyTitle} next={t.models.emptyNext} /> : null}
          <ul className="cards plain">
            {data.seats.map((seat) => (
              <li key={seat.seat} className="mini-card">
                <h3>{seat.seat}</h3>
                <p>{seat.model ? t.models.runsOn(seat.model, seat.provider ?? "") : t.models.noModel}</p>
                <p className="quiet">{t.models.asked(seat.asked_class, seat.effort)}</p>
                {seat.paid_by ? <p className="quiet">{t.models.paidBy(seat.paid_by)}</p> : null}
                {agentOf(seat.seat) ? (
                  <p className="quiet" data-testid="listening-score" title={t.listening.scoreHint}>
                    {t.models.listening(listeningLine(agentOf(seat.seat) ?? {}))}
                  </p>
                ) : null}
                {seat.note ? (
                  <p className="note" data-testid="substitution">
                    {seat.note}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}
