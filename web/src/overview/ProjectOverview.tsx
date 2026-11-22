/**
 * The project at a glance (CHAT-18, CHAT-19, PLN-5, GOV-1): the goal and progress, the budget
 * burn, the crew, a short timeline and the latest deliverables. Each section loads on its own,
 * so one slow or failed part never blanks the page.
 */
import { useMemo, type ReactNode } from "react";
import { ArrowRight, PackageOpen } from "lucide-react";
import { get, type Header } from "../api/client";
import { useAuth } from "../auth";
import { CrewStrip } from "../crew/CrewStrip";
import { doingSentence } from "../crew/logic";
import { DeliverableCard } from "../deliverables/DeliverableCard";
import { arrange, authorKind, defaultScope } from "../deliverables/logic";
import { compactNumber, share } from "../lib/humanize";
import { useLoad, type Loaded } from "../lib/useLoad";
import { overview } from "../strings.crew";
import { Avatar } from "../ui/Avatar";
import { SegmentBar } from "../ui/Progress";
import { Skeleton } from "../ui/Skeleton";
import { BurnChart } from "./BurnChart";
import { hoursLeft } from "./burn";
import { lastsFor, progressOf, projectionSentence, timelineOf } from "./logic";

const TIMELINE_ITEMS = 12;
const LATEST_FILES = 3;
const FEED_PAGE = 200;
/** Feed pages to read at most; the timeline needs only the newest lines. */
const FEED_PAGES = 20;

type Tab = "chat" | "work" | "crew" | "deliverables";
type Panel = "feed" | "budget" | "runs";

interface Props {
  projectId: string;
  changes: number;
  header: Header | null;
  onTab(tab: Tab): void;
  onPanel(panel: Panel): void;
  /** Opens one file in Deliverables. */
  onOpenFile?(name: string): void;
}

async function loadFeed(projectId: string): Promise<Awaited<ReturnType<typeof get<"/v1/record/feed">>>["items"]> {
  const items = [];
  let after: string | undefined;
  for (let page = 0; page < FEED_PAGES; page += 1) {
    const result = await get("/v1/record/feed", { project_id: projectId, after, limit: FEED_PAGE });
    items.push(...result.items);
    if (!result.next) break;
    after = result.next;
  }
  return items;
}

function Section({
  id,
  title,
  action,
  children,
  className = "",
}: {
  id: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={`card ov-card ${className}`} aria-labelledby={id}>
      <header className="card-head">
        <h2 id={id}>{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}

/** The loading, error and empty states every section shares. */
function State<T>({ load, lines = 3, children }: { load: Loaded<T>; lines?: number; children(data: T): ReactNode }): JSX.Element {
  if (load.data !== undefined) return <>{children(load.data)}</>;
  if (load.error) {
    return (
      <div className="ov-error" role="alert">
        <p className="quiet">{overview.sectionError}</p>
        <button type="button" className="button small" onClick={load.reload}>
          {overview.retry}
        </button>
      </div>
    );
  }
  return <Skeleton lines={lines} />;
}

function More({ label, onClick }: { label: string; onClick(): void }): JSX.Element {
  return (
    <button type="button" className="button ghost small ov-more" onClick={onClick}>
      {label}
      <ArrowRight size={14} aria-hidden="true" />
    </button>
  );
}

export function ProjectOverview({ projectId, changes, header, onTab, onPanel, onOpenFile }: Props): JSX.Element {
  const { person } = useAuth();
  const status = useLoad(() => get("/v1/projects/status", { project_id: projectId }), [projectId, changes]);
  const plan = useLoad(() => get("/v1/plan/show", { project_id: projectId }), [projectId, changes]);
  const budget = useLoad(() => get("/v1/budget/show", { project_id: projectId }), [projectId, changes]);
  const feed = useLoad(() => loadFeed(projectId), [projectId, changes]);
  const files = useLoad(() => get("/v1/artifacts/list", { project_id: projectId }), [projectId, changes]);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, changes]);
  const seats = useMemo(() => new Set((roster.data?.seats ?? []).map((seat) => seat.name)), [roster.data]);

  const goalAndProgress = (
    <Section
      id="ov-goal"
      title={overview.goal}
      className="ov-goal"
      action={<More label={overview.openPlan} onClick={() => onTab("work")} />}
    >
      <State load={status} lines={2}>
        {(data) => <p className="ov-goal-text">{data.goal || overview.noGoal}</p>}
      </State>
      <h3 className="eyebrow ov-sub">{overview.progress}</h3>
      <State load={plan} lines={2}>
        {(data) => {
          const progress = progressOf(data.requirements);
          if (progress.counted === 0 && progress.excluded === 0) return <p className="quiet">{overview.noRequirements}</p>;
          return (
            <>
              <SegmentBar segments={progress.segments} label={overview.progressLabel} />
              <ul className="plain legend">
                {progress.segments.map((segment) => (
                  <li key={segment.key} className="legend-item">
                    <span className={`legend-swatch seg-${segment.tone}`} aria-hidden="true" />
                    <strong>{segment.value}</strong>
                    <span>{segment.label}</span>
                  </li>
                ))}
              </ul>
              <p className="ov-projection">{projectionSentence(data.pace, progress.proposed)}</p>
              {data.target ? <p className="quiet">{overview.target(data.target.date, data.target.beside_projection)}</p> : null}
              {data.commitment ? <p className="quiet">{overview.commitment(data.commitment.state, data.commitment.date)}</p> : null}
              {progress.excluded > 0 ? <p className="quiet">{overview.excluded(progress.excluded)}</p> : null}
            </>
          );
        }}
      </State>
    </Section>
  );

  const budgetSection = (
    <Section
      id="ov-budget"
      title={overview.budget}
      className="ov-budget"
      action={<More label={overview.openBudget} onClick={() => onPanel("budget")} />}
    >
      <State load={budget} lines={2}>
        {(data) => {
          const rate = plan.data?.pace.burn_rate ?? null;
          const left = hoursLeft(data.remaining, rate);
          return (
            <div className="ov-budget-lines">
              <p className="ov-budget-headline tabular">
                {overview.budgetLine(compactNumber(data.spent), compactNumber(data.wall), share(data.spent, data.wall))}
              </p>
              <p className="quiet tabular">
                {rate && left !== null
                  ? `${overview.pace(compactNumber(rate))} · ${overview.lasts(lastsFor(left))}`
                  : overview.noPace}
              </p>
              {data.at_wall ? (
                <p className="note note-error" role="status">
                  {overview.atWall}
                </p>
              ) : null}
            </div>
          );
        }}
      </State>
      <BurnChart projectId={projectId} changes={changes} />
    </Section>
  );

  const crewSection = (
    <Section id="ov-crew" title={overview.crew} className="ov-crew" action={<More label={overview.openCrew} onClick={() => onTab("crew")} />}>
      <CrewStrip projectId={projectId} changes={changes} header={header} onOpen={() => onTab("crew")} />
      {header ? (
        header.now.length === 0 ? (
          <p className="quiet ov-nobody">{overview.nobodyWorking}</p>
        ) : (
          <ul className="plain ov-working" aria-live="polite">
            {header.now.map((item) => (
              <li key={`${item.seat}-${item.run_kind}`}>
                <Avatar name={item.seat} size="xs" status="working" />
                <span>
                  <strong>{item.seat}</strong> <span className="quiet">{doingSentence(item.doing, item.run_kind)}</span>
                </span>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </Section>
  );

  const timeline = (
    <Section id="ov-timeline" title={overview.timeline} className="ov-timeline">
      <State load={feed} lines={5}>
        {(items) => {
          const lines = timelineOf(items, TIMELINE_ITEMS);
          if (lines.length === 0) return <p className="quiet">{overview.noActivity}</p>;
          return (
            <ol className="plain ov-events" aria-label={overview.timelineLabel}>
              {lines.map((line) => (
                <li key={line.id} className={`ov-event type-${line.type.split(".")[0]}`}>
                  <span className="ov-event-dot" aria-hidden="true" />
                  <span className="ov-event-text">{line.text}</span>
                  <time className="quiet tabular" dateTime={line.at}>
                    {line.when}
                  </time>
                </li>
              ))}
            </ol>
          );
        }}
      </State>
      <div className="ov-foot">
        <button type="button" className="button small" onClick={() => onPanel("feed")}>
          {overview.seeAll}
        </button>
      </div>
    </Section>
  );

  const latest = (
    <Section
      id="ov-latest"
      title={overview.latest}
      className="ov-latest"
      action={<More label={overview.seeDeliverables} onClick={() => onTab("deliverables")} />}
    >
      <State load={files} lines={3}>
        {(data) => {
          const recent = arrange(data.items, "all", "recent", defaultScope(data.items)).slice(0, LATEST_FILES);
          if (recent.length === 0) {
            return (
              <div className="ov-empty">
                <PackageOpen size={20} aria-hidden="true" />
                <p className="quiet">{overview.noDeliverables}</p>
              </div>
            );
          }
          return (
            <ul className="plain ov-files">
              {recent.map((item) => (
                <li key={item.name}>
                  <DeliverableCard
                    projectId={projectId}
                    item={item}
                    author={authorKind(item, seats)}
                    me={person?.name}
                    compact
                    onOpen={() => (onOpenFile ? onOpenFile(item.name) : onTab("deliverables"))}
                  />
                </li>
              ))}
            </ul>
          );
        }}
      </State>
    </Section>
  );

  return (
    <div className="overview" data-testid="project-overview">
      <div className="ov-main">
        {goalAndProgress}
        {budgetSection}
        {latest}
      </div>
      <div className="ov-side">
        {crewSection}
        {timeline}
      </div>
    </div>
  );
}
