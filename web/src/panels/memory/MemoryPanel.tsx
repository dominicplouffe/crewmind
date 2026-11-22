/** The Memory panel: what agents are given every run, and what the chairman can change about it. */
import { useRef, useState, type KeyboardEvent } from "react";
import { t } from "../../strings";
import { CorrectionsTab } from "./CorrectionsTab";
import { DecisionsTab } from "./DecisionsTab";
import { OrdersTab } from "./OrdersTab";
import { PinnedTab } from "./PinnedTab";
import { PreferencesTab, RecallTab } from "./RecallTab";
import type { TabProps } from "./parts";

const TABS = ["pinned", "orders", "decisions", "corrections", "recall", "preferences"] as const;
type TabId = (typeof TABS)[number];

interface Props extends TabProps {
  onJump(messageId: number): void;
  onFile(name: string): void;
}

export function MemoryPanel(props: Props): JSX.Element {
  const [tab, setTab] = useState<TabId>("pinned");
  const list = useRef<HTMLDivElement>(null);
  const { projectId, changes, onChanged } = props;
  const shared = { projectId, changes, onChanged };

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
    list.current?.querySelector<HTMLElement>(`#memory-tab-${id}`)?.focus();
  };

  let body: JSX.Element;
  switch (tab) {
    case "pinned":
      body = <PinnedTab {...shared} />;
      break;
    case "orders":
      body = <OrdersTab {...shared} />;
      break;
    case "decisions":
      body = <DecisionsTab {...shared} onJump={props.onJump} onFile={props.onFile} />;
      break;
    case "corrections":
      body = <CorrectionsTab {...shared} />;
      break;
    case "recall":
      body = <RecallTab {...shared} />;
      break;
    case "preferences":
      body = <PreferencesTab />;
      break;
  }

  return (
    <>
      {/* Arrow keys move between tabs, as the tabs pattern asks; each tab is also a plain button. */}
      {/* eslint-disable-next-line jsx-a11y/interactive-supports-focus */}
      <div className="tabs" role="tablist" aria-label={t.memory.tabsLabel} ref={list} onKeyDown={onKeyDown}>
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`memory-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="memory-tabpanel"
            tabIndex={tab === id ? 0 : -1}
            onClick={() => setTab(id)}
          >
            {t.memory.tabs[id]}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="memory-tabpanel" aria-labelledby={`memory-tab-${tab}`} data-testid={`memory-${tab}`}>
        {body}
      </div>
    </>
  );
}
