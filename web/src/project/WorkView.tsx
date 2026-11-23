/**
 * Work, board first: the requirements as a compact list (choose one to filter the board), the tasks
 * as a board of columns (a card opens its detail), and the rest of the plan folded under "Plan
 * details". Agents create and move the work; the chairman watches, decides, and can add a requirement.
 */
import { ChevronRight, Plus, RefreshCw, X } from "lucide-react";
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { get, type Task } from "../api/client";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { useNeedsYou } from "../needs/NeedsYou";
import { BoardSection, type BoardTabId } from "../panels/board/BoardPanel";
import { Kanban } from "../panels/board/Kanban";
import { TaskDetail } from "../panels/board/TaskDetail";
import { AddRequirement } from "../panels/plan/AddRequirement";
import { isSettled } from "../panels/plan/logic";
import type { Change } from "../panels/plan/parts";
import { PlanSection, type PlanTabId } from "../panels/plan/PlanPanel";
import { RequirementStrip, entriesFor } from "../panels/plan/RequirementStrip";
import { t } from "../strings";
import { Sheet } from "../ui/Sheet";
import { Skeleton } from "../ui/Skeleton";
import { NeedsSheet } from "./NeedsSheet";

interface Props {
  projectId: string;
  changes: number;
  onChanged(): void;
}

type DetailTab = { from: "plan"; id: PlanTabId } | { from: "board"; id: Exclude<BoardTabId, "tasks"> };

const DETAIL_TABS: DetailTab[] = [
  { from: "plan", id: "scope" },
  { from: "plan", id: "dates" },
  { from: "plan", id: "finish" },
  { from: "plan", id: "items" },
  { from: "plan", id: "agenda" },
  { from: "plan", id: "rehearsal" },
  { from: "board", id: "audit" },
  { from: "board", id: "evidence" },
  { from: "board", id: "launches" },
];

function PlanDetails({
  projectId,
  changes,
  onChanged,
  open,
  onToggle,
  tab,
  onTab,
}: Props & { open: boolean; onToggle(open: boolean): void; tab: DetailTab; onTab(tab: DetailTab): void }): JSX.Element {
  const words = t.plan.work;
  const list = useRef<HTMLDivElement>(null);
  const at = DETAIL_TABS.findIndex((item) => item.id === tab.id);

  const onKeyDown = (event: KeyboardEvent): void => {
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (at + 1) % DETAIL_TABS.length;
    else if (event.key === "ArrowLeft") next = (at - 1 + DETAIL_TABS.length) % DETAIL_TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = DETAIL_TABS.length - 1;
    const item = next === null ? undefined : DETAIL_TABS[next];
    if (!item) return;
    event.preventDefault();
    onTab(item);
    list.current?.querySelector<HTMLElement>(`#work-tab-${item.id}`)?.focus();
  };

  return (
    <details className="work-details" open={open} onToggle={(event) => onToggle(event.currentTarget.open)} id="work-details">
      <summary>
        <ChevronRight size={16} aria-hidden="true" className="work-details-chevron" />
        <span className="work-details-title">{words.details}</span>
        <span className="quiet work-details-hint">{words.detailsHint}</span>
      </summary>
      {open ? (
        <div className="work-details-body">
          {/* Arrow keys move between tabs, as the tabs pattern asks; each tab is also a plain button. */}
          {/* eslint-disable-next-line jsx-a11y/interactive-supports-focus */}
          <div className="tabs" role="tablist" aria-label={words.detailsLabel} ref={list} onKeyDown={onKeyDown}>
            {DETAIL_TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                id={`work-tab-${item.id}`}
                aria-selected={tab.id === item.id}
                aria-controls="work-tabpanel"
                tabIndex={tab.id === item.id ? 0 : -1}
                onClick={() => onTab(item)}
              >
                {words.detailTabs[item.id] ?? item.id}
              </button>
            ))}
          </div>
          <div role="tabpanel" id="work-tabpanel" aria-labelledby={`work-tab-${tab.id}`} data-testid={`work-${tab.id}`}>
            {tab.from === "plan" ? (
              <PlanSection projectId={projectId} changes={changes} onChanged={onChanged} tab={tab.id} />
            ) : (
              <BoardSection projectId={projectId} changes={changes} onChanged={onChanged} tab={tab.id} />
            )}
          </div>
        </div>
      ) : null}
    </details>
  );
}

export function WorkView({ projectId, changes, onChanged }: Props): JSX.Element {
  const plan = useLoad(() => get("/v1/plan/show", { project_id: projectId }), [projectId, changes]);
  const status = useLoad(() => get("/v1/projects/status", { project_id: projectId }), [projectId, changes]);
  const tasks = useLoad(() => get("/v1/tasks/list", { project_id: projectId }), [projectId, changes]);
  const desk = useNeedsYou().forProject(projectId);
  const [filter, setFilter] = useState<number | null>(null);
  const [openTask, setOpenTask] = useState<Task | null>(null);
  const [deciding, setDeciding] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>({ from: "plan", id: "scope" });
  const words = t.plan.work;
  const board = t.board.kanban;

  const requirements = useMemo(() => plan.data?.requirements ?? [], [plan.data]);
  const texts = useMemo(() => new Map(requirements.map((item) => [item.id, item.text])), [requirements]);
  const items = tasks.data?.items ?? [];
  const explore = status.data?.type === "explore";
  const filtered = filter !== null && requirements.some((item) => item.id === filter) ? filter : null;
  const shownCount = filtered === null ? items.length : items.filter((task) => task.requirement_id === filtered).length;

  const { reload: reloadPlan } = plan;
  const apply = async (change: Change): Promise<void> => {
    await change();
    reloadPlan();
    onChanged();
  };

  const showBets = (): void => {
    setDetailTab({ from: "plan", id: "scope" });
    setDetailsOpen(true);
    requestAnimationFrame(() => document.getElementById("work-details")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  return (
    <div className="work-view work" data-testid="work-view">
      <section className="work-section" aria-labelledby="work-reqs-title">
        <header className="work-head">
          <h2 id="work-reqs-title">
            {words.requirements}
            {requirements.length > 0 ? <span className="work-head-count tabular">{requirements.length}</span> : null}
          </h2>
          <span className="spacer" />
          {!explore && status.data && !adding ? (
            <button type="button" className="button small" onClick={() => setAdding(true)}>
              <Plus size={14} aria-hidden="true" />
              {words.add}
            </button>
          ) : null}
        </header>
        <ErrorNote error={plan.error ?? status.error} />
        {adding && status.data ? (
          <AddRequirement
            projectId={projectId}
            apply={apply}
            type={status.data.type}
            others={requirements.filter((item) => !isSettled(item.state))}
            onDone={() => setAdding(false)}
          />
        ) : null}
        {!plan.data && !plan.error ? <Skeleton lines={3} label={t.plan.work.requirements} /> : null}
        {plan.data && requirements.length === 0 ? (
          explore ? (
            <p className="work-empty">
              {words.emptyExplore}{" "}
              <button type="button" className="work-link" onClick={showBets}>
                {words.showBets}
              </button>
            </p>
          ) : (
            <p className="work-empty">{words.empty}</p>
          )
        ) : null}
        {requirements.length > 0 ? (
          <RequirementStrip
            requirements={requirements}
            tasks={items}
            desk={desk}
            selected={filtered}
            onSelect={setFilter}
            onDecide={setDeciding}
          />
        ) : null}
      </section>

      <section className="work-section" aria-labelledby="work-board-title">
        <header className="work-head">
          <h2 id="work-board-title">
            {board.title}
            {tasks.data ? <span className="work-head-count tabular">{shownCount}</span> : null}
          </h2>
          {filtered !== null ? (
            <span className="work-filter">
              <span>{board.showing(t.plan.scope.name(filtered))}</span>
              <button type="button" className="button ghost icon-only small" onClick={() => setFilter(null)} aria-label={board.showAll}>
                <X size={14} aria-hidden="true" />
              </button>
            </span>
          ) : null}
          <span className="spacer" />
          <button type="button" className="button small ghost" onClick={tasks.reload} disabled={tasks.loading}>
            <RefreshCw size={14} aria-hidden="true" />
            {t.board.refresh}
          </button>
        </header>
        <ErrorNote error={tasks.error} />
        {!tasks.data && !tasks.error ? <Skeleton lines={4} label={board.label} /> : null}
        {tasks.data && items.length === 0 ? (
          <div className="work-board-empty">
            <p className="empty-title">{board.emptyTitle}</p>
            <p className="quiet">{board.emptyNext}</p>
          </div>
        ) : null}
        {tasks.data && items.length > 0 ? (
          <>
            {filtered !== null && shownCount === 0 ? <p className="work-empty">{board.emptyFilteredNext}</p> : null}
            <Kanban tasks={items} requirements={texts} filter={filtered} onOpen={setOpenTask} />
          </>
        ) : null}
      </section>

      <PlanDetails
        projectId={projectId}
        changes={changes}
        onChanged={onChanged}
        open={detailsOpen}
        onToggle={setDetailsOpen}
        tab={detailTab}
        onTab={setDetailTab}
      />

      {openTask ? (
        <Sheet title={openTask.title} subtitle={board.sheetSubtitle(openTask.id, openTask.team)} onClose={() => setOpenTask(null)} testId="work-task-sheet">
          <TaskDetail projectId={projectId} changes={changes} taskId={openTask.id} onBack={() => setOpenTask(null)} variant="sheet" />
        </Sheet>
      ) : null}
      {deciding !== null ? (
        <NeedsSheet
          projectName={status.data?.name ?? ""}
          entries={entriesFor(desk, deciding)}
          onClose={() => setDeciding(null)}
          onChanged={onChanged}
        />
      ) : null}
    </div>
  );
}
