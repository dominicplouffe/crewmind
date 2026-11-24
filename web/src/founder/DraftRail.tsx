/**
 * The draft as it stands, beside the conversation, read like a project brief (FND-3): its name and
 * facts, the goal, the squad, settings it changes and steps the Founder had to redo. How it grades
 * and whether it is rehearsed are on the checklist, not here. The long parts open on request.
 */
import { useState } from "react";
import { Markdown, Pre } from "../components/common";
import { formatDateTime, formatNumber, formatValue } from "../lib/format";
import { t } from "../strings";
import type { DraftSummary } from "./logic";

interface Props {
  draft: DraftSummary | null;
  /** Steps of the Founder that the server did not accept. */
  rulesHit: Record<string, unknown>[];
}

const word = (value: unknown): string => (typeof value === "string" ? value : "");

export function ProjectFacts({ draft }: { draft: DraftSummary }): JSX.Element {
  const words = t.founder.side;
  const types: Record<string, string> = t.projects.types;
  return (
    <dl className="pairs">
      <div>
        <dt>{words.name}</dt>
        <dd data-testid="draft-name">{draft.name}</dd>
      </div>
      <div>
        <dt>{words.type}</dt>
        <dd>{types[draft.type] ?? draft.type}</dd>
      </div>
      {draft.budgetTokens !== null ? (
        <div>
          <dt>{words.budget}</dt>
          <dd>{words.budgetTokens(formatNumber(draft.budgetTokens))}</dd>
        </div>
      ) : null}
      {draft.quality ? (
        <div>
          <dt>{words.quality}</dt>
          <dd>{draft.quality}</dd>
        </div>
      ) : null}
      {draft.payingCredential ? (
        <div>
          <dt>{words.pays}</dt>
          <dd>{draft.payingCredential}</dd>
        </div>
      ) : null}
      {draft.deadline ? (
        <div>
          <dt>{words.deadline}</dt>
          <dd>
            {formatDateTime(draft.deadline.date)}
            {draft.deadline.source ? ` (${draft.deadline.source})` : ""}
          </dd>
        </div>
      ) : null}
    </dl>
  );
}

export function SquadList({ draft }: { draft: DraftSummary }): JSX.Element {
  const words = t.founder.side;
  if (draft.teams.length === 0) return <p className="quiet">{words.noTeams}</p>;
  return (
    <ul className="squad-list">
      {draft.teams.map((team) => (
        <li key={team.name} data-testid="draft-team">
          <p className="squad-team">
            {team.name} <span className="badge squad-role">{team.role}</span>
          </p>
          <p className="squad-members">{team.members.join(", ")}</p>
        </li>
      ))}
    </ul>
  );
}

export function SettingsList({ draft }: { draft: DraftSummary }): JSX.Element {
  return (
    <dl className="pairs">
      {draft.settings.map(([name, value]) => (
        <div key={name}>
          <dt>{name}</dt>
          <dd>{typeof value === "object" && value !== null ? <Pre>{formatValue(value)}</Pre> : formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The goal, clamped to its first lines until the person asks for the rest. */
function Goal({ goal }: { goal: string }): JSX.Element {
  const words = t.founder.brief;
  const [whole, setWhole] = useState(false);
  const long = goal.length > 480;
  return (
    <div className="brief-goal">
      <h3 className="rail-subtitle">{words.goal}</h3>
      <div className={long && !whole ? "goal-text clamped" : "goal-text"}>
        <Markdown source={goal} className="draft-goal" />
      </div>
      {long ? (
        <button type="button" className="button ghost small" aria-expanded={whole} onClick={() => setWhole((value) => !value)}>
          {whole ? words.goalLess : words.goalMore}
        </button>
      ) : null}
    </div>
  );
}

export function DraftRail({ draft, rulesHit }: Props): JSX.Element {
  const words = t.founder.side;
  const brief = t.founder.brief;
  const rail = t.founder.draftRail;
  const seats = draft ? draft.teams.reduce((count, team) => count + team.members.length, 0) : 0;
  return (
    <section className="rail-card brief" aria-labelledby="draft-title" data-testid="draft">
      <header className="rail-head">
        <h2 id="draft-title">{brief.title}</h2>
      </header>
      {draft ? (
        <>
          <ProjectFacts draft={draft} />
          {draft.goal ? <Goal goal={draft.goal} /> : null}
          <div className="brief-squad">
            <h3 className="rail-subtitle">
              {brief.squad} <span className="rail-count">{rail.seats(seats)}</span>
            </h3>
            <SquadList draft={draft} />
          </div>
          {draft.settings.length > 0 ? (
            <details className="fold">
              <summary>{rail.settingsShow(draft.settings.length)}</summary>
              <SettingsList draft={draft} />
            </details>
          ) : null}
          {rulesHit.length > 0 ? (
            <details className="fold" data-testid="rules-hit">
              <summary>{rail.redone(rulesHit.length)}</summary>
              <p className="quiet">{words.rulesHitIntro}</p>
              <ul className="redone-list">
                {rulesHit.map((hit, index) => (
                  <li key={index}>{words.ruleHit(word(hit.rule), word(hit.code) || word(hit.tool), word(hit.message))}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : (
        <p className="quiet">{brief.empty}</p>
      )}
    </section>
  );
}
