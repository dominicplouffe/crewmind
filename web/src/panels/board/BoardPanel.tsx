/** The Board panel: what the agents are working on, and what has and has not been checked. */
import { useRef, useState, type KeyboardEvent } from "react";
import { t } from "../../strings";
import { AuditTab } from "./AuditTab";
import { EvidenceTab } from "./EvidenceTab";
import { LaunchesTab } from "./LaunchesTab";
import { TasksTab } from "./TasksTab";
import type { BoardTabProps } from "./parts";

const TABS = ["tasks", "audit", "evidence", "launches"] as const;
type TabId = (typeof TABS)[number];

interface Props extends BoardTabProps {
  /** Tells the page something changed, so the chat header and other views reload. */
  onChanged(): void;
}

export function BoardPanel({ projectId, changes, onChanged }: Props): JSX.Element {
  const [tab, setTab] = useState<TabId>("tasks");
  const list = useRef<HTMLDivElement>(null);
  const shared = { projectId, changes };

  const onKeyDown = (event: KeyboardEvent): void => {
    const at = TABS.indexOf(tab);
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (at + 1) % TABS.length;
    else if (event.key === "ArrowLeft") next = (at - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    const id = next === null ? undefined : TABS[next];
    if (!id) return;
    event.preventDefault();
    setTab(id);
    list.current?.querySelector<HTMLElement>(`#board-tab-${id}`)?.focus();
  };

  let body: JSX.Element;
  switch (tab) {
    case "tasks":
      body = <TasksTab {...shared} />;
      break;
    case "audit":
      body = <AuditTab {...shared} onChanged={onChanged} />;
      break;
    case "evidence":
      body = <EvidenceTab {...shared} />;
      break;
    case "launches":
      body = <LaunchesTab {...shared} onChanged={onChanged} />;
      break;
  }

  return (
    <>
      {/* Arrow keys move between tabs, as the tabs pattern asks; each tab is also a plain button. */}
      {/* eslint-disable-next-line jsx-a11y/interactive-supports-focus */}
      <div className="tabs" role="tablist" aria-label={t.board.tabsLabel} ref={list} onKeyDown={onKeyDown}>
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`board-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="board-tabpanel"
            tabIndex={tab === id ? 0 : -1}
            onClick={() => setTab(id)}
          >
            {t.board.tabs[id]}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="board-tabpanel" aria-labelledby={`board-tab-${tab}`} data-testid={`board-${tab}`}>
        {body}
      </div>
    </>
  );
}
