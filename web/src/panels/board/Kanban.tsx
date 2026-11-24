/**
 * The board as columns: Ready, In progress, In review, Blocked, Done, and Other for a state this page
 * does not know (never dropped). Agents move the cards; people watch, and open a card for its detail.
 * On a phone the columns scroll sideways and snap; the column row above jumps to one.
 */
import { useRef, type CSSProperties } from "react";
import type { Task } from "../../api/client";
import { t } from "../../strings";
import { boardColumns, showsCheckLabel, slug, type BoardColumn, type ColumnId } from "./logic";
import { AgentText, CheckLabel, StateTag } from "./parts";
import { AgentAvatar, useAgentName } from "../../squad/names";

/** The state each column is named for; a card in another state also shows its own. */
const PRIMARY: Record<ColumnId, string | null> = {
  ready: "ready",
  progress: "claimed",
  review: "review",
  blocked: "blocked",
  done: "done",
  other: null,
};

interface Props {
  tasks: Task[];
  /** Requirement texts by id, for each card's requirement chip. */
  requirements: Map<number, string>;
  /** Only this requirement's tasks, or all when null. */
  filter: number | null;
  onOpen(task: Task): void;
}

function TaskCard({ task, column, requirement, onOpen }: { task: Task; column: ColumnId; requirement: string | undefined; onOpen(): void }): JSX.Element {
  const nameOf = useAgentName();
  const holder = task.claimant ? nameOf(task.claimant).name : null;
  const words = t.board.kanban;
  const ownState = task.state !== PRIMARY[column] && task.state !== task.label;
  return (
    <button type="button" className={`task-card state-${slug(task.state)}`} onClick={onOpen} data-testid="board-card" data-task-id={task.id}>
      <span className="task-card-title">{task.title}</span>
      {task.requirement_id != null ? (
        <span className="task-card-req" title={requirement}>
          <span className="task-card-req-id tabular">
            <span className="visually-hidden">{words.requirement(task.requirement_id)}: </span>
            <span aria-hidden="true">{task.requirement_id}</span>
          </span>
          {requirement ? <span className="task-card-req-text">{requirement}</span> : null}
        </span>
      ) : null}
      {task.parent_id != null ? <span className="task-card-sub">{words.subtaskOf(task.parent_id)}</span> : null}
      {task.state === "blocked" && task.reason ? (
        <span className="task-card-reason">
          <span className="visually-hidden">{words.why}: </span>
          <AgentText text={task.reason} />
        </span>
      ) : null}
      <span className="task-card-foot">
        {task.claimant ? (
          <span className="task-card-who">
            <AgentAvatar seat={task.claimant} size="xs" />
            <span className="visually-hidden">{words.heldBy(holder ?? task.claimant)}</span>
            <span aria-hidden="true">{holder}</span>
          </span>
        ) : (
          <span className="task-card-who quiet">{words.unclaimed}</span>
        )}
        {task.team ? <span className="task-card-team">{words.team(task.team)}</span> : null}
        <span className="task-card-tags">
          {ownState ? <StateTag state={task.state} /> : null}
          {showsCheckLabel(task) ? <CheckLabel label={task.label} /> : null}
        </span>
      </span>
      {task.failures > 0 ? <span className="task-card-fail">{t.board.tasks.failures(task.failures)}</span> : null}
    </button>
  );
}

function Column({ column, requirements, onOpen }: { column: BoardColumn<Task>; requirements: Map<number, string>; onOpen(task: Task): void }): JSX.Element {
  const words = t.board.kanban;
  const name = words.columns[column.id] ?? column.id;
  return (
    <section className={`kanban-col col-${column.id}`} aria-labelledby={`kanban-${column.id}`} id={`kanban-col-${column.id}`}>
      <h3 className="kanban-col-head" id={`kanban-${column.id}`}>
        <span className={`kanban-dot dot-${column.id}`} aria-hidden="true" />
        <span>{name}</span>
        <span className="kanban-count tabular">
          <span className="visually-hidden">: </span>
          {column.tasks.length}
        </span>
      </h3>
      {column.tasks.length === 0 ? (
        <p className="kanban-empty">{words.empty}</p>
      ) : (
        <ul className="plain kanban-list" aria-label={words.columnLabel(name, column.tasks.length)}>
          {column.tasks.map((task) => (
            <li key={task.id}>
              <TaskCard
                task={task}
                column={column.id}
                requirement={task.requirement_id != null ? requirements.get(task.requirement_id) : undefined}
                onOpen={() => onOpen(task)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function Kanban({ tasks, requirements, filter, onOpen }: Props): JSX.Element {
  const words = t.board.kanban;
  const board = useRef<HTMLDivElement>(null);
  const columns = boardColumns(tasks, filter);

  const jump = (id: ColumnId): void => {
    const target = board.current?.querySelector<HTMLElement>(`#kanban-col-${id}`);
    target?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
    target?.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
  };

  return (
    <div className="kanban-wrap">
      <nav className="kanban-jump" aria-label={words.jumpLabel}>
        {columns.map((column) => (
          <button key={column.id} type="button" className={`kanban-jump-item col-${column.id}`} onClick={() => jump(column.id)}>
            <span className={`kanban-dot dot-${column.id}`} aria-hidden="true" />
            {words.columns[column.id] ?? column.id}
            <span className="kanban-count tabular">{column.tasks.length}</span>
          </button>
        ))}
      </nav>
      <div className="kanban" ref={board} style={{ "--columns": columns.length } as CSSProperties}>
        {columns.map((column) => (
          <Column key={column.id} column={column} requirements={requirements} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}
