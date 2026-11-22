/**
 * The Plan panel: what is in scope, when it will be done and what it will cost, how the project
 * finishes, the decision items filed for the chairman, and what the clock will do next.
 */
import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { get } from "../../api/client";
import { ErrorNote, Loading } from "../../components/common";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { ServerNote, useAct } from "../memory/parts";
import { AgendaTab } from "./AgendaTab";
import { DatesTab } from "./DatesTab";
import { FinishTab } from "./FinishTab";
import { ItemsTab } from "./ItemsTab";
import type { Change, PlanTabProps } from "./parts";
import { ScopeTab } from "./ScopeTab";

const TABS = ["scope", "dates", "finish", "items", "agenda"] as const;
type TabId = (typeof TABS)[number];

interface Props {
  projectId: string;
  /** Changes whenever the live stream reports a change in the project, so the panel reloads. */
  changes: number;
  /** Tells the page something changed, so the chat header and other views reload. */
  onChanged(): void;
}

export function PlanPanel({ projectId, changes, onChanged }: Props): JSX.Element {
  const [tab, setTab] = useState<TabId>("scope");
  const [note, setNote] = useState<string | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const plan = useLoad(() => get("/v1/plan/show", { project_id: projectId }), [projectId, changes]);
  const status = useLoad(() => get("/v1/projects/status", { project_id: projectId }), [projectId, changes]);
  const act = useAct(onChanged);

  const { setData } = plan;
  const apply = useCallback(
    async (change: Change): Promise<void> => {
      const view = await change();
      setData(view);
      setNote(view.note ?? null);
    },
    [setData],
  );
  const { run: runAct } = act;
  const run = useCallback((change: Change): Promise<boolean> => runAct(() => apply(change)), [runAct, apply]);
  const applyAndTell = useCallback(
    async (change: Change): Promise<void> => {
      await apply(change);
      onChanged();
    },
    [apply, onChanged],
  );

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
    list.current?.querySelector<HTMLElement>(`#plan-tab-${id}`)?.focus();
  };

  let body: JSX.Element | null = null;
  // Decision items and the agenda are loaded by their own tabs; the others show the plan.
  if (tab === "items") body = <ItemsTab projectId={projectId} changes={changes} onChanged={onChanged} />;
  else if (tab === "agenda") body = <AgendaTab projectId={projectId} changes={changes} />;
  else if (plan.data && status.data) {
    const shared: PlanTabProps = {
      projectId,
      plan: plan.data,
      type: status.data.type,
      state: status.data.state,
      busy: act.busy,
      refusal: act.error,
      run,
      apply: applyAndTell,
    };
    switch (tab) {
      case "scope":
        body = <ScopeTab {...shared} />;
        break;
      case "dates":
        body = <DatesTab {...shared} />;
        break;
      default:
        body = (
          <FinishTab
            {...shared}
            changes={changes}
            onFinished={() => {
              plan.reload();
              status.reload();
              onChanged();
            }}
          />
        );
        break;
    }
  }

  return (
    <>
      {/* Arrow keys move between tabs, as the tabs pattern asks; each tab is also a plain button. */}
      {/* eslint-disable-next-line jsx-a11y/interactive-supports-focus */}
      <div className="tabs" role="tablist" aria-label={t.plan.tabsLabel} ref={list} onKeyDown={onKeyDown}>
        {TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`plan-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="plan-tabpanel"
            tabIndex={tab === id ? 0 : -1}
            onClick={() => setTab(id)}
          >
            {t.plan.tabs[id]}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="plan-tabpanel" aria-labelledby={`plan-tab-${tab}`} data-testid={`plan-${tab}`}>
        <div className="row wrap board-bar">
          <span className="spacer" />
          <button
            type="button"
            className="button small"
            disabled={plan.loading}
            onClick={() => {
              plan.reload();
              status.reload();
            }}
          >
            {t.plan.refresh}
          </button>
        </div>
        <ErrorNote error={plan.error ?? status.error} />
        <ErrorNote error={act.error} />
        <ServerNote text={note} />
        {!body && !plan.error && !status.error ? <Loading /> : null}
        {body}
      </div>
    </>
  );
}
