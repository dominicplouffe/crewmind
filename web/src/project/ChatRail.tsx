/**
 * Beside the conversation on wide screens: what needs you here, the crew at work, and where the
 * project stands. Each part opens its full view. Hidden on smaller screens, where the header line
 * and the Overview tab carry the same facts.
 */
import { ArrowRight, Inbox } from "lucide-react";
import type { Header } from "../api/client";
import type { PanelId } from "../chat/panels";
import { CrewStrip } from "../crew/CrewStrip";
import { compactNumber, fromNow, share } from "../lib/humanize";
import { urgencyOf, type DeskEntry } from "../needs/summary";
import { BurnChart } from "../overview/BurnChart";
import { t } from "../strings";
import { projectLayout } from "../strings.shell";
import type { ProjectTab } from "./ProjectTop";

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
  return (
    <aside className="chat-rail" aria-label={projectLayout.rail}>
      <section className="rail-section" aria-labelledby="rail-needs">
        <h2 id="rail-needs">{projectLayout.railNeeds}</h2>
        {needs.length === 0 ? (
          <p className="quiet">{projectLayout.railNeedsEmpty}</p>
        ) : (
          <ul className="plain rail-needs">
            {needs.slice(0, 4).map((entry, index) => (
              <li key={entry.item ? entry.item.id : `${entry.what}-${index}`}>
                <button type="button" className={`rail-need urgency-${urgencyOf(entry)}`} onClick={onNeeds}>
                  <Inbox size={14} aria-hidden="true" />
                  <span className="rail-need-text">
                    <span className="rail-need-title">{entry.title}</span>
                    {entry.deadline ? <span className="quiet">{fromNow(entry.deadline)}</span> : null}
                  </span>
                </button>
              </li>
            ))}
            {needs.length > 0 ? (
              <li>
                <button type="button" className="button small primary rail-review" onClick={onNeeds}>
                  {projectLayout.railReview}
                  <ArrowRight size={14} aria-hidden="true" />
                </button>
              </li>
            ) : null}
          </ul>
        )}
      </section>
      <section className="rail-section" aria-labelledby="rail-crew">
        <h2 id="rail-crew">{projectLayout.tabs.crew}</h2>
        <CrewStrip projectId={projectId} changes={changes} header={header} onOpen={() => onTab("crew")} />
      </section>
      {header ? (
        <section className="rail-section" aria-labelledby="rail-budget">
          <h2 id="rail-budget">{t.header.budget}</h2>
          <button type="button" className="rail-budget" onClick={() => onPanel("budget")}>
            <span className="tabular">
              {compactNumber(header.budget_spent)} of {compactNumber(header.budget_wall)} tokens
            </span>
            <span className="quiet">{share(header.budget_spent, header.budget_wall)} used</span>
          </button>
          <BurnChart projectId={projectId} changes={changes} compact />
        </section>
      ) : null}
      {header && header.next.length > 0 ? (
        <section className="rail-section" aria-labelledby="rail-next">
          <h2 id="rail-next">{t.header.next}</h2>
          <ul className="plain quiet rail-next">
            {header.next.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <button type="button" className="button ghost small" onClick={() => onTab("overview")}>
        {projectLayout.tabs.overview}
        <ArrowRight size={14} aria-hidden="true" />
      </button>
    </aside>
  );
}
