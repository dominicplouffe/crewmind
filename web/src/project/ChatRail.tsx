/**
 * Beside the conversation on wide screens: the company at work (CHAT-18, EXE-4, GOV-1, PLN).
 * In the order a chairman asks: who is working on what, how far the goal has come and when it
 * should finish, what happens next, what was just delivered, and what it costs. Each part opens its
 * full view. What waits on the chairman is told once, in one line, since the header and the chat
 * carry it in full. Hidden on smaller screens, where the header line and the Overview tab carry
 * the same facts.
 */
import { useMemo, type ReactNode } from "react";
import { ArrowRight, CalendarClock, Inbox } from "lucide-react";
import { get, type Header } from "../api/client";
import type { PanelId } from "../chat/panels";
import { arrange, defaultScope } from "../deliverables/logic";
import { fromNow } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import type { DeskEntry } from "../needs/summary";
import { budgetWords, progressOf, projectionSentence } from "../overview/logic";
import { nowEntries } from "../overview/now";
import { FileIcon, Load, NowList } from "../overview/parts";
import { story } from "../strings.overview";
import { Meter, SegmentBar } from "../ui/Progress";
import type { ProjectTab } from "./ProjectTop";
import { AgentAvatar, useAgentName } from "../crew/names";

const NOW_SHOWN = 4;
const FILES_SHOWN = 3;

interface Props {
  projectId: string;
  changes: number;
  header: Header | null;
  needs: DeskEntry[];
  onNeeds(): void;
  onTab(tab: ProjectTab): void;
  onPanel(panel: PanelId): void;
}

/** One part of the rail: a heading, a link to its full view, and what it says. */
function Part({
  id,
  title,
  aside,
  open,
  openLabel,
  children,
}: {
  id: string;
  title: string;
  aside?: ReactNode;
  open?(): void;
  openLabel?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <section className="rail-part" aria-labelledby={id} data-testid={id}>
      <header className="rail-part-head">
        <h2 id={id}>{title}</h2>
        {aside ? <span className="rail-part-aside">{aside}</span> : null}
        {open && openLabel ? (
          <button type="button" className="rail-part-open" onClick={open}>
            {openLabel}
            <ArrowRight size={12} aria-hidden="true" />
          </button>
        ) : null}
      </header>
      {children}
    </section>
  );
}

export function ChatRail({ projectId, changes, header, needs, onNeeds, onTab, onPanel }: Props): JSX.Element {
  const words = story.rail;
  const tasks = useLoad(() => get("/v1/tasks/list", { project_id: projectId }), [projectId, changes]);
  const files = useLoad(() => get("/v1/artifacts/list", { project_id: projectId }), [projectId, changes]);
  const budget = useLoad(() => get("/v1/budget/show", { project_id: projectId }), [projectId, changes]);
  const plan = useLoad(() => get("/v1/plan/show", { project_id: projectId }), [projectId, changes]);
  const nameOf = useAgentName();
  const working = useMemo(() => header?.now ?? [], [header]);
  const now = useMemo(
    () => (tasks.data ? nowEntries(working, tasks.data.items, (seat) => nameOf(seat).name) : []),
    [working, tasks.data, nameOf],
  );

  return (
    <aside className="chat-rail rail" aria-label={words.label}>
      {needs.length > 0 ? (
        <button type="button" className="rail-needs-line" onClick={onNeeds}>
          <Inbox size={14} aria-hidden="true" />
          <span>{words.needs(needs.length)}</span>
          <span className="rail-needs-go">
            {words.review}
            <ArrowRight size={12} aria-hidden="true" />
          </span>
        </button>
      ) : null}

      <Part
        id="rail-now"
        title={words.now}
        aside={
          working.length > 0 ? (
            <span className="rail-working">
              <span className="avatar-stack" aria-hidden="true">
                {working.slice(0, 3).map((work) => (
                  <AgentAvatar key={work.seat} seat={work.seat} size="xs" status="working" />
                ))}
              </span>
              {words.atWork(working.length)}
            </span>
          ) : null
        }
        open={() => onTab("work")}
        openLabel={words.openWork}
      >
        <Load load={tasks} lines={3}>
          {() => <NowList entries={now} limit={NOW_SHOWN} onMore={() => onTab("work")} compact />}
        </Load>
      </Part>

      <Part id="rail-progress" title={words.progress} open={() => onTab("work")} openLabel={words.openPlan}>
        <Load load={plan} lines={2}>
          {(data) => {
            const summary = progressOf(data.requirements);
            if (summary.counted === 0) return <p className="quiet rail-line">{story.progress.none}</p>;
            return (
              <>
                <p className="rail-figure">
                  <span className="tabular">{words.met(summary.met, summary.counted)}</span>
                  {summary.active > 0 ? <span className="quiet">{words.inProgress(summary.active)}</span> : null}
                </p>
                <SegmentBar segments={summary.segments} label={story.progress.label} />
                <p className="rail-line">{projectionSentence(data.pace, summary.proposed)}</p>
              </>
            );
          }}
        </Load>
      </Part>

      {header && header.next.length > 0 ? (
        <Part id="rail-next" title={words.next} open={() => onPanel("feed")} openLabel={words.openActivity}>
          <ul className="plain rail-next">
            {header.next.map((line, index) => (
              <li key={index}>
                <CalendarClock size={14} aria-hidden="true" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </Part>
      ) : null}

      <Part id="rail-delivered" title={words.delivered} open={() => onTab("deliverables")} openLabel={words.allFiles}>
        <Load load={files} lines={2}>
          {(data) => {
            const recent = arrange(data.items, "all", "recent", defaultScope(data.items)).slice(0, FILES_SHOWN);
            if (recent.length === 0) return <p className="quiet rail-line">{words.deliveredEmpty}</p>;
            return (
              <ul className="plain rail-files">
                {recent.map((item) => (
                  <li key={item.name}>
                    <button type="button" className="rail-file" onClick={() => onTab("deliverables")}>
                      <span className="rail-file-icon">
                        <FileIcon name={item.name} mediaType={item.media_type} size={14} />
                      </span>
                      <span className="rail-file-text">
                        <span className="rail-file-name">{item.name}</span>
                        <span className="rail-file-meta">
                          {nameOf(item.last_author).name} · {fromNow(item.last_change)}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            );
          }}
        </Load>
      </Part>

      <Part id="rail-budget" title={words.budget} open={() => onPanel("budget")} openLabel={words.openBudget}>
        <Load load={budget} lines={2}>
          {(data) => {
            const said = budgetWords(data, plan.data?.pace.burn_rate ?? null);
            const tone = data.at_wall || data.spent >= data.wrapup_at ? "danger" : data.spent >= data.warn_at ? "warning" : "accent";
            return (
              <>
                <p className="rail-figure">
                  <span className="tabular">{said.used}</span>
                  <span className="quiet tabular">{story.budget.share(said.share)}</span>
                </p>
                <Meter value={data.spent} max={data.wall} label={story.budget.meterLabel(said.share)} tone={tone} />
                <p className="rail-line">{data.at_wall ? story.budget.atWall : (said.paceShort ?? story.budget.noPace)}</p>
              </>
            );
          }}
        </Load>
      </Part>

      <button type="button" className="button ghost small rail-overview" onClick={() => onTab("overview")}>
        {words.overview}
        <ArrowRight size={14} aria-hidden="true" />
      </button>
    </aside>
  );
}
