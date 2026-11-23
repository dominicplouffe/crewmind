/**
 * Beside the conversation on wide screens: the company at work (CHAT-18, EXE-4, GOV-1). Who is
 * doing what now, what was just delivered, the budget and its pace, and what comes next. What
 * waits on the chairman is told once, in one line, since the header and the chat carry it in full.
 * Hidden on smaller screens, where the header line and the Overview tab carry the same facts.
 */
import { useMemo } from "react";
import { ArrowRight, Inbox } from "lucide-react";
import { get, type Header } from "../api/client";
import type { PanelId } from "../chat/panels";
import { arrange, defaultScope } from "../deliverables/logic";
import { fromNow } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import type { DeskEntry } from "../needs/summary";
import { BurnChart } from "../overview/BurnChart";
import { budgetWords } from "../overview/logic";
import { nowEntries } from "../overview/now";
import { FileIcon, Load, NowList } from "../overview/parts";
import { story } from "../strings.overview";
import { Meter } from "../ui/Progress";
import type { ProjectTab } from "./ProjectTop";

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

export function ChatRail({ projectId, changes, header, needs, onNeeds, onTab, onPanel }: Props): JSX.Element {
  const words = story.rail;
  const tasks = useLoad(() => get("/v1/tasks/list", { project_id: projectId }), [projectId, changes]);
  const files = useLoad(() => get("/v1/artifacts/list", { project_id: projectId }), [projectId, changes]);
  const budget = useLoad(() => get("/v1/budget/show", { project_id: projectId }), [projectId, changes]);
  const plan = useLoad(() => get("/v1/plan/show", { project_id: projectId }), [projectId, changes]);
  const now = useMemo(() => (tasks.data ? nowEntries(header?.now ?? [], tasks.data.items) : []), [header, tasks.data]);

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

      <section className="rail-section" aria-labelledby="rail-now">
        <h2 id="rail-now">{words.now}</h2>
        <Load load={tasks} lines={3}>
          {() => <NowList entries={now} limit={NOW_SHOWN} onMore={() => onTab("work")} compact />}
        </Load>
      </section>

      <section className="rail-section" aria-labelledby="rail-delivered">
        <h2 id="rail-delivered">{words.delivered}</h2>
        <Load load={files} lines={2}>
          {(data) => {
            const recent = arrange(data.items, "all", "recent", defaultScope(data.items)).slice(0, FILES_SHOWN);
            if (recent.length === 0) return <p className="quiet ov-quiet-line">{words.deliveredEmpty}</p>;
            return (
              <ul className="plain rail-files">
                {recent.map((item) => (
                  <li key={item.name}>
                    <button
                      type="button"
                      className="rail-file"
                      onClick={() => onTab("deliverables")}
                      aria-label={words.openFile(item.name, item.last_author)}
                    >
                      <span className="rail-file-icon">
                        <FileIcon name={item.name} mediaType={item.media_type} size={14} />
                      </span>
                      <span className="rail-file-text">
                        <span className="rail-file-name">{item.name}</span>
                        <span className="rail-file-meta">
                          {item.last_author} · {fromNow(item.last_change)}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            );
          }}
        </Load>
      </section>

      <section className="rail-section" aria-labelledby="rail-budget">
        <h2 id="rail-budget">{words.budget}</h2>
        <Load load={budget} lines={2}>
          {(data) => {
            const said = budgetWords(data, plan.data?.pace.burn_rate ?? null);
            const tone = data.at_wall || data.spent >= data.wrapup_at ? "danger" : data.spent >= data.warn_at ? "warning" : "accent";
            return (
              <button type="button" className="rail-budget" onClick={() => onPanel("budget")}>
                <span className="rail-budget-figure">
                  <span className="tabular">{said.used}</span>
                  <span className="quiet tabular">{story.budget.share(said.share)}</span>
                </span>
                <Meter value={data.spent} max={data.wall} label={story.budget.meterLabel(said.share)} tone={tone} />
                <span className="rail-budget-pace">{data.at_wall ? story.budget.atWall : (said.paceShort ?? story.budget.noPace)}</span>
              </button>
            );
          }}
        </Load>
        <BurnChart projectId={projectId} changes={changes} compact />
      </section>

      {header && header.next.length > 0 ? (
        <section className="rail-section" aria-labelledby="rail-next">
          <h2 id="rail-next">{words.next}</h2>
          <ul className="plain rail-next">
            {header.next.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <button type="button" className="button ghost small rail-overview" onClick={() => onTab("overview")}>
        {words.overview}
        <ArrowRight size={14} aria-hidden="true" />
      </button>
    </aside>
  );
}
