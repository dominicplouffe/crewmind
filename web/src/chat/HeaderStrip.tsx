/** The always-visible project header (CHAT-18): now, next, waiting on you, budget, state and holds. */
import type { Header } from "../api/client";
import { Markdown } from "../components/common";
import { percent } from "../lib/format";
import { t } from "../strings";
import type { PanelId } from "./panels";

interface Props {
  header: Header | null;
  onOpen(panel: PanelId): void;
  onAction(action: "start" | "hold" | "resume"): void;
}

/** Which button fits which state. The server still decides whether the action is allowed. */
const ACTION_FOR_STATE: Record<string, "start" | "hold" | "resume"> = {
  draft: "start",
  running: "hold",
  held: "resume",
  paused: "resume",
};

export function HeaderStrip({ header, onOpen, onAction }: Props): JSX.Element {
  if (!header) {
    return (
      <section className="strip" aria-label={t.header.label}>
        <p className="quiet" role="status">
          {t.common.loading}
        </p>
      </section>
    );
  }
  const action = ACTION_FOR_STATE[header.state];
  const used = percent(header.budget_spent, header.budget_wall);
  return (
    <section className="strip" aria-label={t.header.label}>
      <div className="strip-item strip-state">
        <span className="strip-label">{t.header.state}</span>
        <span className={`badge state-${header.state}`} data-testid="project-state">
          {header.state}
        </span>
        {action ? (
          <button type="button" className="button small" onClick={() => onAction(action)}>
            {t.header.actions[action]}
          </button>
        ) : null}
      </div>
      <div className="strip-item">
        <button type="button" className="strip-open" onClick={() => onOpen("runs")}>
          <span className="strip-label">{t.header.now}</span>
        </button>
        {header.now.length === 0 ? (
          <span className="quiet">{t.header.nowEmpty}</span>
        ) : (
          <ul className="plain">
            {header.now.map((work, index) => (
              <li key={`${work.seat}-${index}`}>{t.header.working(work.seat, work.doing)}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="strip-item">
        <button type="button" className="strip-open" onClick={() => onOpen("feed")}>
          <span className="strip-label">{t.header.next}</span>
        </button>
        {header.next.length === 0 ? (
          <span className="quiet">{t.header.nextEmpty}</span>
        ) : (
          <ul className="plain">
            {header.next.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="strip-item">
        <span className="strip-label">{t.header.waiting}</span>
        <span data-testid="waiting-count">{t.header.waitingCount(header.waiting_on_you)}</span>
      </div>
      <div className="strip-item strip-budget">
        <button type="button" className="strip-open" onClick={() => onOpen("budget")}>
          <span className="strip-label">{t.header.budget}</span>
        </button>
        <span id="strip-budget-text">{header.budget}</span>
        <progress max={100} value={used} aria-labelledby="strip-budget-text" />
      </div>
      {header.holds.length > 0 ? (
        <div className="strip-item strip-wide">
          <span className="strip-label">{t.header.holds}</span>
          <ul className="plain">
            {header.holds.map((hold, index) => (
              <li key={index} className="hold">
                <Markdown source={t.header.hold(hold.reason, hold.lifts)} className="inline" />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {header.notes.length > 0 ? (
        <div className="strip-item strip-wide">
          <span className="strip-label">{t.header.notes}</span>
          <ul className="plain">
            {header.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {header.unread > 0 ? <span className="visually-hidden">{t.header.unread(header.unread)}</span> : null}
    </section>
  );
}
