/**
 * The project told as a story (CHAT-18, CHAT-19, PLN-5, GOV-1, EXE-4): one sentence on where it
 * stands, who is doing what now, progress by requirement, the budget and its pace, the crew, what
 * happened, and the latest deliverables. Each part loads on its own, so one slow or failed part
 * never blanks the page. Display only: the server decides every state and number.
 */
import { useMemo, type ReactNode } from "react";
import { ArrowRight, CircleCheck, CircleDot, OctagonAlert, PackageOpen, Pause, Play, Square } from "lucide-react";
import { get, type Header } from "../api/client";
import { useAuth } from "../auth";
import { CrewStrip } from "../crew/CrewStrip";
import { DeliverableCard } from "../deliverables/DeliverableCard";
import { arrange, authorKind, defaultScope } from "../deliverables/logic";
import { useLoad } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { story } from "../strings.overview";
import { Meter, SegmentBar } from "../ui/Progress";
import { BurnChart } from "./BurnChart";
import { budgetWords, headlineOf, progressOf, projectionSentence, requirementRows, type HeadlineTone } from "./logic";
import { nowEntries } from "./now";
import { Load, More, NowList } from "./parts";
import { Timeline } from "./Timeline";
import { storyOf } from "./timeline";

const TIMELINE_ENTRIES = 12;
const LATEST_FILES = 3;
const FEED_PAGE = 200;
/** Feed pages to read at most; the story needs only the newest lines. */
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

const TONE_ICON: Record<HeadlineTone, typeof Play> = {
  neutral: CircleDot,
  steady: Play,
  attention: OctagonAlert,
  held: Pause,
  stopped: Square,
  done: CircleCheck,
};

export function ProjectOverview({ projectId, changes, header, onTab, onPanel, onOpenFile }: Props): JSX.Element {
  const { person } = useAuth();
  const status = useLoad(() => get("/v1/projects/status", { project_id: projectId }), [projectId, changes]);
  const plan = useLoad(() => get("/v1/plan/show", { project_id: projectId }), [projectId, changes]);
  const budget = useLoad(() => get("/v1/budget/show", { project_id: projectId }), [projectId, changes]);
  const tasks = useLoad(() => get("/v1/tasks/list", { project_id: projectId }), [projectId, changes]);
  const items = useLoad(() => get("/v1/items/list", { project_id: projectId }), [projectId, changes]);
  const feed = useLoad(() => loadFeed(projectId), [projectId, changes]);
  const files = useLoad(() => get("/v1/artifacts/list", { project_id: projectId }), [projectId, changes]);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, changes]);
  const seats = useMemo(() => new Set((roster.data?.seats ?? []).map((seat) => seat.name)), [roster.data]);

  const headline = useMemo(() => {
    const state = header?.state ?? status.data?.state;
    if (!state || !plan.data || !tasks.data || !budget.data) return null;
    return headlineOf({
      state,
      holds: header?.holds ?? [],
      atWall: budget.data.at_wall,
      requirements: plan.data.requirements,
      tasks: tasks.data.items,
      spent: budget.data.spent,
      wall: budget.data.wall,
    });
  }, [header, status.data, plan.data, tasks.data, budget.data]);

  const now = useMemo(() => (tasks.data ? nowEntries(header?.now ?? [], tasks.data.items) : null), [header, tasks.data]);

  const days = useMemo(() => {
    if (!feed.data || !tasks.data || !plan.data) return null;
    return storyOf(
      {
        feed: feed.data,
        tasks: tasks.data.items,
        requirements: plan.data.requirements,
        items: items.data?.items ?? [],
        files: files.data?.items ?? [],
        me: person?.person_id ?? null,
      },
      TIMELINE_ENTRIES,
    );
  }, [feed.data, tasks.data, plan.data, items.data, files.data, person]);

  const hero = (
    <section className="ov-hero" aria-label={story.headline.label} aria-live="polite">
      {headline ? (
        <>
          <p className={`ov-headline tone-${headline.tone}`}>
            <span className="ov-lead">
              {(() => {
                const Icon = TONE_ICON[headline.tone];
                return <Icon size={14} aria-hidden="true" />;
              })()}
              {headline.lead}
            </span>
            <span className="ov-facts">{headline.facts}</span>
          </p>
          {headline.blocked ? (
            <div className="ov-blocked">
              <OctagonAlert size={16} aria-hidden="true" />
              <p>
                <AgentText className="ov-title" text={headline.blocked.title} /> {story.headline.blockedOne}
                {headline.blocked.others > 0 ? ` ${story.headline.blockedMore(headline.blocked.others)}` : null}
                {headline.blocked.reason ? (
                  <>
                    {": "}
                    <AgentText className="ov-reason" text={headline.blocked.reason} />
                  </>
                ) : null}
              </p>
              <button type="button" className="button small" onClick={() => onTab("work")}>
                {story.headline.openWork}
                <ArrowRight size={14} aria-hidden="true" />
              </button>
            </div>
          ) : null}
        </>
      ) : status.error || plan.error || tasks.error || budget.error ? (
        <div className="ov-error" role="alert">
          <p className="quiet">{story.sectionError}</p>
          <button
            type="button"
            className="button small"
            onClick={() => {
              status.reload();
              plan.reload();
              tasks.reload();
              budget.reload();
            }}
          >
            {story.retry}
          </button>
        </div>
      ) : (
        <span className="skeleton ov-hero-skel" aria-hidden="true" />
      )}
      {status.data?.goal ? (
        <p className="ov-goal">
          <span className="eyebrow">{story.headline.goal}</span>
          <AgentText text={status.data.goal} />
        </p>
      ) : null}
    </section>
  );

  const nowSection = (
    <Section id="ov-now" title={story.now.title} className="ov-now-card" action={<More label={story.headline.openWork} onClick={() => onTab("work")} />}>
      <Load load={tasks} lines={3}>
        {() => <NowList entries={now ?? []} />}
      </Load>
    </Section>
  );

  const progress = (
    <Section id="ov-progress" title={story.progress.title} className="ov-progress" action={<More label={story.progress.openPlan} onClick={() => onTab("work")} />}>
      <Load load={plan} lines={4}>
        {(data) => {
          const summary = progressOf(data.requirements);
          if (summary.counted === 0 && summary.excluded === 0) return <p className="quiet ov-quiet-line">{story.progress.none}</p>;
          const rows = requirementRows(data.requirements, tasks.data?.items ?? []);
          return (
            <>
              <SegmentBar segments={summary.segments} label={story.progress.label} />
              <ul className="plain legend">
                {summary.segments
                  .filter((segment) => segment.value > 0)
                  .map((segment) => (
                    <li key={segment.key} className="legend-item">
                      <span className={`legend-swatch seg-${segment.tone}`} aria-hidden="true" />
                      <strong>{segment.value}</strong>
                      <span>{segment.label}</span>
                    </li>
                  ))}
              </ul>
              <ol className="plain ov-reqs">
                {rows.map((row) => (
                  <li key={row.id} className={`ov-req tone-${row.tone}`}>
                    <span className={`ov-req-state seg-text-${row.tone}`}>
                      <span className={`legend-swatch seg-${row.tone}`} aria-hidden="true" />
                      {row.stateWord}
                    </span>
                    <AgentText className="ov-req-text" text={row.text} />
                    <span className="ov-req-tasks">
                      {row.total > 0 ? (
                        <Meter value={row.done} max={row.total} label={story.progress.tasksLabel(row.text, row.done, row.total)} />
                      ) : null}
                      <span className="quiet tabular">{story.progress.tasks(row.done, row.total)}</span>
                    </span>
                  </li>
                ))}
              </ol>
              <p className="ov-projection">{projectionSentence(data.pace, summary.proposed)}</p>
              {data.target ? <p className="quiet ov-aside">{story.progress.target(data.target.date, data.target.beside_projection)}</p> : null}
              {data.commitment ? <p className="quiet ov-aside">{story.progress.commitment(data.commitment.state, data.commitment.date)}</p> : null}
              {summary.excluded > 0 ? <p className="quiet ov-aside">{story.progress.excluded(summary.excluded)}</p> : null}
            </>
          );
        }}
      </Load>
    </Section>
  );

  const budgetSection = (
    <Section id="ov-budget" title={story.budget.title} className="ov-budget" action={<More label={story.budget.open} onClick={() => onPanel("budget")} />}>
      <Load load={budget} lines={2}>
        {(data) => {
          const words = budgetWords(data, plan.data?.pace.burn_rate ?? null);
          return (
            <div className="ov-budget-lines">
              <p className="ov-budget-figure">
                <span className="ov-budget-used">{words.used}</span>
                <span className="ov-budget-share tabular">{story.budget.share(words.share)}</span>
              </p>
              <p className="quiet">{words.pace}</p>
              {data.at_wall ? (
                <p className="note note-error" role="status">
                  {story.budget.atWall}
                </p>
              ) : null}
            </div>
          );
        }}
      </Load>
      <BurnChart projectId={projectId} changes={changes} />
    </Section>
  );

  const crewSection = (
    <Section id="ov-crew" title={story.crew.title} className="ov-crew">
      <CrewStrip projectId={projectId} changes={changes} header={header} onOpen={() => onTab("crew")} />
    </Section>
  );

  const timeline = (
    <Section id="ov-timeline" title={story.timeline.title} className="ov-timeline" action={<More label={story.timeline.seeAll} onClick={() => onPanel("feed")} />}>
      <Load load={feed} lines={5}>
        {() => (days ? <Timeline days={days} me={person?.name} /> : <span className="skeleton ov-hero-skel" aria-hidden="true" />)}
      </Load>
    </Section>
  );

  const latest = (
    <Section id="ov-latest" title={story.latest.title} className="ov-latest" action={<More label={story.latest.open} onClick={() => onTab("deliverables")} />}>
      <Load load={files} lines={3}>
        {(data) => {
          const recent = arrange(data.items, "all", "recent", defaultScope(data.items)).slice(0, LATEST_FILES);
          if (recent.length === 0) {
            return (
              <div className="ov-empty">
                <PackageOpen size={20} aria-hidden="true" />
                <p className="quiet">{story.latest.empty}</p>
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
      </Load>
    </Section>
  );

  return (
    <div className="overview" data-testid="project-overview">
      {hero}
      <div className="ov-columns">
        <div className="ov-main">
          {nowSection}
          {progress}
          {latest}
        </div>
        <div className="ov-side">
          {budgetSection}
          {crewSection}
          {timeline}
        </div>
      </div>
    </div>
  );
}
