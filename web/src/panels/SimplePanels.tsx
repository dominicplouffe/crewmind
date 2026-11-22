/**
 * The read-only panels: activity feed (OBS), budget (GOV-3) and models (LLM-3). Numbers are put in
 * words with a sense of scale; every figure comes from the server.
 */
import { Activity, Bot, Gauge, Sparkles, UserRound } from "lucide-react";
import { get, type Seat } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { formatNumber } from "../lib/format";
import { compactNumber, share } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { Avatar } from "../ui/Avatar";
import { Meter } from "../ui/Progress";
import { RelativeTime } from "../chat/RelativeTime";
import { groupByDay } from "../desk/logic";
import { Empty, Loading } from "./kit";
import { listeningLine } from "./memory/PinnedTab";

interface Props {
  projectId: string;
  /** Changes whenever the project changes, so the panel reloads. */
  changes: number;
}

type FeedItem = Awaited<ReturnType<typeof get<"/v1/record/feed">>>["items"][number];

async function loadFeed(projectId: string): Promise<FeedItem[]> {
  const items = [];
  let after: string | undefined;
  for (;;) {
    const page = await get("/v1/record/feed", { project_id: projectId, after, limit: 200 });
    items.push(...page.items);
    if (!page.next) return items;
    after = page.next;
  }
}

const PERSON_ID = /^[0-9a-f]{32}$/;

/** A CSS length for a share of a whole, for drawing only. */
function percentOf(part: number, whole: number): string {
  return whole > 0 ? `${Math.min(100, Math.max(0, (part / whole) * 100))}%` : "0%";
}
const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" });

/** Who did it: you, someone else in the project (a person or an agent, by id), or crewmind itself (a job). */
function Actor({ actor, me }: { actor: string; me: { id: string; name: string } | null }): JSX.Element {
  if (me && actor === me.id) return <Avatar name={me.name} kind="person" size="xs" label={t.feed.you} />;
  if (PERSON_ID.test(actor)) {
    return (
      <span className="feed-system is-member" role="img" aria-label={t.feed.person}>
        <UserRound size={11} aria-hidden="true" />
      </span>
    );
  }
  return (
    <span className="feed-system" role="img" aria-label={t.feed.crewmind}>
      <Sparkles size={11} aria-hidden="true" />
    </span>
  );
}

export function FeedPanel({ projectId, changes }: Props): JSX.Element {
  const feed = useLoad(() => loadFeed(projectId), [projectId, changes]);
  const person = useAuth().person;
  const me = person ? { id: person.person_id, name: person.name } : null;
  const days = groupByDay(feed.data ?? []).reverse();
  return (
    <>
      <ErrorNote error={feed.error} />
      {feed.loading && !feed.data ? <Loading lines={8} /> : null}
      {feed.data && days.length === 0 ? <Empty icon={Activity} title={t.feed.emptyTitle} next={t.feed.emptyNext} /> : null}
      {/* One list, newest first, with a heading row for each day. */}
      <ol className="feed plain" aria-label={t.feed.listLabel}>
        {days.map((day) => (
          <li key={day.day} className="feed-day">
            <p className="eyebrow feed-day-title">{dayFormat.format(day.date)}</p>
            <ol className="plain" aria-label={t.feed.dayLabel(dayFormat.format(day.date))}>
              {[...day.lines].reverse().map((item) => (
                <li key={item.id} className="feed-line">
                  <Actor actor={item.actor} me={me} />
                  <span className="feed-text">{item.text}</span>
                  <RelativeTime at={item.at} className="feed-time" />
                </li>
              ))}
            </ol>
          </li>
        ))}
      </ol>
    </>
  );
}

export function BudgetPanel({ projectId, changes }: Props): JSX.Element {
  const budget = useLoad(() => get("/v1/budget/show", { project_id: projectId }), [projectId, changes]);
  const data = budget.data;
  const words = t.budget;
  if (!data) {
    return (
      <>
        <ErrorNote error={budget.error} />
        {budget.loading ? <Loading lines={5} /> : null}
      </>
    );
  }
  const used = compactNumber(data.spent);
  const wall = compactNumber(data.wall);
  const spentShare = share(data.spent, data.wall);
  const tone = data.at_wall ? "danger" : data.spent >= data.wrapup_at ? "warning" : "accent";
  const levels: { key: string; line: string; passed: boolean }[] = [
    {
      key: "warn",
      line: words.levels.warn(compactNumber(data.warn_at), share(data.warn_at, data.wall)),
      passed: data.spent >= data.warn_at,
    },
    {
      key: "wrapup",
      line: words.levels.wrapup(compactNumber(data.wrapup_at), share(data.wrapup_at, data.wall)),
      passed: data.spent >= data.wrapup_at,
    },
    { key: "wall", line: words.levels.wall(wall), passed: data.at_wall },
  ];
  const kinds = Object.entries(data.by_kind);
  const kindTotal = kinds.reduce((sum, [, count]) => sum + Number(count), 0);
  return (
    <>
      <ErrorNote error={budget.error} />
      <section className="budget-hero" aria-labelledby="budget-summary">
        <p className="budget-figure" id="budget-summary" title={data.summary}>
          <span className="budget-used">{words.headline(used, wall)}</span>{" "}
          <span className="quiet">{words.share(spentShare)}</span>
        </p>
        <Meter value={data.spent} max={data.wall} label={words.meterLabel(used, wall, spentShare)} tone={tone} />
        <div className="budget-scale" aria-hidden="true">
          <span className="budget-mark" style={{ left: percentOf(data.warn_at, data.wall) }} />
          <span className="budget-mark is-wrapup" style={{ left: percentOf(data.wrapup_at, data.wall) }} />
        </div>
        <p className="quiet">{words.left(compactNumber(data.remaining))}</p>
      </section>
      {data.at_wall ? (
        <p className="note note-error" role="status">
          {words.atWall}
        </p>
      ) : null}
      <dl className="pairs budget-pairs">
        <div>
          <dt>{words.used}</dt>
          <dd className="tabular">{words.tokens(formatNumber(data.spent))}</dd>
        </div>
        <div>
          <dt>{words.remaining}</dt>
          <dd className="tabular">{words.tokens(formatNumber(data.remaining))}</dd>
        </div>
        <div>
          <dt>{words.wall}</dt>
          <dd className="tabular">{words.tokens(formatNumber(data.wall))}</dd>
        </div>
      </dl>
      <h3 className="group-title">{words.levelsTitle}</h3>
      <ol className="levels plain">
        {levels.map((level) => (
          <li key={level.key} className={level.passed ? "level is-passed" : "level"}>
            <Gauge size={16} aria-hidden="true" />
            <span>
              {level.line}
              {level.passed ? <span className="badge level-passed">{words.passed}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      <h3 className="group-title">{words.byKind}</h3>
      <table className="grid budget-kinds">
        <thead>
          <tr>
            <th scope="col">{words.kind}</th>
            <th scope="col" className="num">
              {words.tokensHead}
            </th>
          </tr>
        </thead>
        <tbody>
          {kinds.map(([kind, count]) => {
            const label = words.kinds[kind as keyof typeof words.kinds] ?? kind.replace(/_/g, " ");
            return (
              <tr key={kind}>
                <th scope="row">
                  {label}
                  <span className="kind-bar" aria-hidden="true">
                    <span style={{ width: percentOf(Number(count), kindTotal) }} />
                  </span>
                </th>
                <td className="num" title={formatNumber(Number(count))}>
                  {compactNumber(Number(count))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="quiet">{words.cacheNote}</p>
    </>
  );
}

export function ModelsPanel({ projectId, changes }: Props): JSX.Element {
  const models = useLoad(() => get("/v1/models/show", { project_id: projectId }), [projectId, changes]);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, changes]);
  const data = models.data;
  const words = t.models;
  const agentOf = (name: string): Seat | undefined => roster.data?.seats.find((seat) => seat.name === name);
  return (
    <>
      <ErrorNote error={models.error} />
      {models.loading && !data ? <Loading lines={5} /> : null}
      {data ? (
        <>
          <section className="quality-card" aria-labelledby="quality-title">
            <p className="eyebrow" id="quality-title">
              {words.qualityTitle}
            </p>
            <p className="lead">{words.quality(data.quality)}</p>
            <p className="quiet">{words.qualityLevels[data.quality] ?? words.qualityOther}</p>
            <p className="quiet">{words.qualityHint}</p>
          </section>
          {data.seats.length === 0 ? <Empty icon={Bot} title={words.emptyTitle} next={words.emptyNext} /> : null}
          <ul className="rows plain">
            {data.seats.map((seat) => {
              const agent = agentOf(seat.seat);
              return (
                <li key={seat.seat} className="seat-row">
                  <Avatar name={seat.seat} kind="agent" size="md" />
                  <div className="row-main">
                    <h3 className="row-heading">{seat.seat}</h3>
                    <p className="quiet">
                      {agent && agent.role !== seat.seat ? agent.role : (words.seatKinds[seat.kind] ?? seat.kind)}
                    </p>
                    <p className="seat-model">{seat.model ? words.runsOn(seat.model, seat.provider ?? "") : words.noModel}</p>
                    <p className="quiet">
                      {words.thinking(
                        words.classes[seat.asked_class] ?? seat.asked_class,
                        words.efforts[seat.effort] ?? seat.effort,
                      )}
                    </p>
                    {seat.paid_by ? <p className="quiet">{words.paidBy(seat.paid_by)}</p> : null}
                    {agent ? (
                      <p className="quiet" data-testid="listening-score" title={t.listening.scoreHint}>
                        {words.listening(listeningLine(agent))}
                      </p>
                    ) : null}
                    {seat.note ? (
                      <p className="note note-warning" data-testid="substitution">
                        {seat.note}
                      </p>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </>
  );
}
