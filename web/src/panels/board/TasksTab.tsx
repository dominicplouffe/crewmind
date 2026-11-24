/** Tasks, grouped by state, with subtasks under their parent. People only watch: agents create and close them. */
import { ListChecks } from "lucide-react";
import { useId, useState } from "react";
import { get, type Task } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { Empty, Loading } from "../kit";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { groupTasks, type TaskGroup } from "./logic";
import { Bar, CheckLabel, StateTag, type BoardTabProps } from "./parts";
import { TaskDetail } from "./TaskDetail";
import { useAgentName } from "../../squad/names";

/** Indentation stops growing here, so deep subtasks still fit a phone. */
const MAX_INDENT = 3;

function Group({ group, onSelect }: { group: TaskGroup<Task>; onSelect(id: number): void }): JSX.Element {
  const words = t.board.tasks;
  const nameOf = useAgentName();
  return (
    <section data-testid="task-group" data-state={group.state}>
      <h3 className="group-title">
        <span className="cap">{words.group(group.state, group.rows.length)}</span>
      </h3>
      <ul className="records plain" aria-label={words.listLabel(group.state)}>
        {group.rows.map(({ task, depth }) => (
          <li key={task.id} data-testid="task" data-task-id={task.id} className={`depth-${Math.min(depth, MAX_INDENT)}`}>
            <button type="button" className="row-title task-title" onClick={() => onSelect(task.id)}>
              {depth > 0 ? <span className="visually-hidden">{words.subtask}: </span> : null}
              {task.title}
            </button>
            <p className="quiet row wrap">
              <StateTag state={task.state} />
              <CheckLabel label={task.label} />
              {task.claimant ? <span>{words.heldBy(nameOf(task.claimant).name)}</span> : task.team ? <span>{words.team(task.team)}</span> : null}
              {task.failures > 0 ? <span data-testid="task-failures">{words.failures(task.failures)}</span> : null}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function TasksTab({ projectId, changes }: BoardTabProps): JSX.Element {
  const [openOnly, setOpenOnly] = useState(false);
  const [showClosed, setShowClosed] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const openOnlyId = useId();
  const tasks = useLoad(
    () => get("/v1/tasks/list", { project_id: projectId, open_only: openOnly ? true : undefined }),
    [projectId, changes, openOnly],
  );
  const words = t.board.tasks;

  if (selected !== null) {
    return <TaskDetail projectId={projectId} changes={changes} taskId={selected} onBack={() => setSelected(null)} />;
  }

  const items = tasks.data?.items ?? [];
  const grouped = groupTasks(items);
  return (
    <>
      <Bar onRefresh={tasks.reload} busy={tasks.loading}>
        <span className="check-field">
          <input id={openOnlyId} type="checkbox" checked={openOnly} onChange={(event) => setOpenOnly(event.target.checked)} />
          <label htmlFor={openOnlyId}>{words.openOnly}</label>
        </span>
      </Bar>
      <ErrorNote error={tasks.error} />
      {tasks.loading && !tasks.data ? <Loading /> : null}
      {tasks.data && items.length === 0 ? (
        openOnly ? (
          <Empty icon={ListChecks} title={words.emptyOpenTitle} next={words.emptyOpenNext} />
        ) : (
          <Empty icon={ListChecks} title={words.emptyTitle} next={words.emptyNext} />
        )
      ) : null}
      {grouped.open.map((group) => (
        <Group key={group.state} group={group} onSelect={setSelected} />
      ))}
      {grouped.closedCount > 0 ? (
        <>
          <button type="button" className="button small ghost closed-toggle" aria-expanded={showClosed} onClick={() => setShowClosed((value) => !value)}>
            {showClosed ? words.hideClosed : words.showClosed(grouped.closedCount)}
          </button>
          {showClosed ? grouped.closed.map((group) => <Group key={group.state} group={group} onSelect={setSelected} />) : null}
        </>
      ) : null}
    </>
  );
}
