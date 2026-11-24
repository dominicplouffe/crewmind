/**
 * The requirements as one compact list above the board: each one's state, its text, how many of its
 * tasks are done, who holds its work, and whether it waits on the chairman. Choosing one filters the
 * board to its tasks. The decision itself is answered in its decision card (`onDecide`), and every
 * other action on a requirement stays in the plan's Scope section.
 */
import { useState } from "react";
import type { Task } from "../../api/client";
import type { DeskEntry } from "../../needs/summary";
import { t } from "../../strings";
import { Pill } from "../../ui/Status";
import { requirementProgress } from "../board/logic";
import { AgentText } from "../board/parts";
import { isSettled } from "./logic";
import { StateTag, type Requirement } from "./parts";
import { AgentAvatar, useAgentName } from "../../squad/names";

/** Cut and declined requirements are folded away; met ones stay, as progress. */
function isDropped(state: string): boolean {
  return isSettled(state) && state !== "met";
}

interface Props {
  requirements: Requirement[];
  tasks: Task[];
  /** This project's desk entries; an entry about a requirement names it in `item.fields.requirement_id`. */
  desk: DeskEntry[];
  selected: number | null;
  onSelect(id: number | null): void;
  /** Opens the decision cards about this requirement. */
  onDecide(requirementId: number): void;
}

/** The desk entries about one requirement. */
export function entriesFor(desk: readonly DeskEntry[], id: number): DeskEntry[] {
  return desk.filter((entry) => entry.item?.fields.requirement_id === id);
}

function Row({
  requirement,
  tasks,
  desk,
  selected,
  onSelect,
  onDecide,
}: { requirement: Requirement } & Omit<Props, "requirements">): JSX.Element {
  const words = t.plan.work;
  const nameOf = useAgentName();
  const progress = requirementProgress(tasks, requirement.id);
  const owners = progress.owners.map((seat) => nameOf(seat).name);
  const waiting = entriesFor(desk, requirement.id);
  const pressed = selected === requirement.id;
  const percent = progress.total === 0 ? 0 : Math.round((progress.done / progress.total) * 100);
  return (
    <li
      className={`req${pressed ? " is-selected" : ""}${isSettled(requirement.state) ? " is-past" : ""}${waiting.length ? " needs-you" : ""}`}
      data-testid="work-requirement"
      data-requirement-id={requirement.id}
    >
      <button type="button" className="req-main" aria-pressed={pressed} onClick={() => onSelect(pressed ? null : requirement.id)}>
        <span className="req-id tabular">
          <span className="visually-hidden">{t.plan.scope.name(requirement.id)}</span>
          <span aria-hidden="true">{requirement.id}</span>
        </span>
        <StateTag state={requirement.state} />
        <span className="req-text">
          <AgentText text={requirement.text} />
        </span>
        <span className="req-progress">
          <span className="req-bar" aria-hidden="true">
            <span style={{ width: `${percent}%` }} />
          </span>
          <span className="tabular">{words.progress(progress.done, progress.total)}</span>
        </span>
        <span className="req-owners">
          {progress.owners.length > 0 ? (
            <>
              <span className="avatar-stack" aria-hidden="true" title={owners.join(", ")}>
                {progress.owners.map((seat) => (
                  <AgentAvatar key={seat} seat={seat} size="xs" />
                ))}
              </span>
              <span className="visually-hidden">{words.owners(owners.join(", "))}</span>
            </>
          ) : null}
        </span>
      </button>
      {waiting.length > 0 ? (
        <span className="req-needs">
          <Pill tone="warning">{words.needsYou}</Pill>
          <button type="button" className="button small" onClick={() => onDecide(requirement.id)} aria-label={words.decideOn(requirement.id)}>
            {words.decide}
          </button>
        </span>
      ) : null}
    </li>
  );
}

export function RequirementStrip({ requirements, ...rest }: Props): JSX.Element {
  const words = t.plan.work;
  const [showDropped, setShowDropped] = useState(false);
  const ordered = [...requirements].sort((a, b) => a.stage - b.stage || a.id - b.id);
  const kept = ordered.filter((requirement) => !isDropped(requirement.state));
  const dropped = ordered.filter((requirement) => isDropped(requirement.state));
  const shown = showDropped ? [...kept, ...dropped] : kept;
  return (
    <>
      <ul className="plain req-list" aria-label={words.listLabel}>
        {shown.map((requirement) => (
          <Row key={requirement.id} requirement={requirement} {...rest} />
        ))}
      </ul>
      {dropped.length > 0 ? (
        <button type="button" className="button small ghost req-dropped" aria-expanded={showDropped} onClick={() => setShowDropped((value) => !value)}>
          {showDropped ? words.hideSettled : words.settled(dropped.length)}
        </button>
      ) : null}
    </>
  );
}
