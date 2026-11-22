/** Work, full width: the plan (requirements, dates, finish) and the board (tasks, audits, evidence). */
import { useState } from "react";
import { BoardPanel } from "../panels/board/BoardPanel";
import { PlanPanel } from "../panels/plan/PlanPanel";
import { projectLayout } from "../strings.shell";

interface Props {
  projectId: string;
  changes: number;
  onChanged(): void;
}

export function WorkView({ projectId, changes, onChanged }: Props): JSX.Element {
  const [view, setView] = useState<"plan" | "board">("plan");
  const words = projectLayout.work;
  return (
    <div className="work-view">
      <div className="segmented work-switch" role="group" aria-label={words.label}>
        {(["plan", "board"] as const).map((id) => (
          <button key={id} type="button" aria-pressed={view === id} onClick={() => setView(id)}>
            {words[id]}
          </button>
        ))}
      </div>
      <h2 className="visually-hidden">{words[view]}</h2>
      {view === "plan" ? (
        <PlanPanel projectId={projectId} changes={changes} onChanged={onChanged} />
      ) : (
        <BoardPanel projectId={projectId} changes={changes} onChanged={onChanged} />
      )}
    </div>
  );
}
