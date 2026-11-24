/**
 * The draft as it stands, beside the conversation: what the project is, who is on the squad, how
 * the goal grades and what the rehearsal found. Short by default; the long parts (the goal's
 * text, the grade of each element, steps the Founder redid) open on request.
 */
import { Markdown, Pre } from "../components/common";
import { formatDateTime, formatNumber, formatValue } from "../lib/format";
import { t } from "../strings";
import { GoalGrade } from "./GoalGrade";
import type { DraftSummary, Grade } from "./logic";

interface Props {
  draft: DraftSummary | null;
  grade: Grade | null;
  /** The verdict of the rehearsal of this draft, when it has been rehearsed. */
  rehearsal: string | null;
  /** Steps of the Founder that the server did not accept. */
  rulesHit: Record<string, unknown>[];
  /** On the review screen everything is shown open. */
  open?: boolean;
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
          <p className="squad-team">{words.team(team.name, team.role)}</p>
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

export function DraftRail({ draft, grade, rehearsal, rulesHit, open = false }: Props): JSX.Element {
  const words = t.founder.side;
  const rail = t.founder.draftRail;
  const seats = draft ? draft.teams.reduce((count, team) => count + team.members.length, 0) : 0;
  return (
    <div className="rail-stack">
      <section className="rail-card" aria-labelledby="draft-title" data-testid="draft">
        <header className="rail-head">
          <h2 id="draft-title">{rail.title}</h2>
        </header>
        {draft ? (
          <>
            <ProjectFacts draft={draft} />
            <details className="fold" open={open}>
              <summary>{rail.goalShow}</summary>
              <Markdown source={draft.goal} className="draft-goal" />
            </details>
            {draft.settings.length > 0 ? (
              <details className="fold" open={open}>
                <summary>{rail.settingsShow(draft.settings.length)}</summary>
                <SettingsList draft={draft} />
              </details>
            ) : null}
          </>
        ) : (
          <p className="quiet">{words.draftEmpty}</p>
        )}
      </section>
      {draft ? (
        <section className="rail-card" aria-labelledby="squad-title">
          <header className="rail-head">
            <h2 id="squad-title">{rail.squad}</h2>
            <span className="rail-count">{rail.seats(seats)}</span>
          </header>
          <SquadList draft={draft} />
        </section>
      ) : null}
      <section className="rail-card" aria-labelledby="checks-title">
        <header className="rail-head">
          <h2 id="checks-title">{words.grade}</h2>
          {grade ? (
            <span className={grade.ready ? "badge grade-present" : "badge grade-missing"}>
              {grade.ready ? words.gradeReady : words.gradeNotReady}
            </span>
          ) : null}
        </header>
        {grade ? (
          <>
            <p data-testid="grade-summary">{grade.summary}</p>
            <details className="fold" open={open}>
              <summary>{rail.gradeShow}</summary>
              <GoalGrade grade={grade} />
            </details>
          </>
        ) : (
          <p className="quiet">{words.gradeEmpty}</p>
        )}
        <h3 className="rail-subtitle">{words.rehearsal}</h3>
        <p className={rehearsal ? undefined : "quiet"} data-testid="draft-rehearsal">
          {rehearsal ?? words.rehearsalNone}
        </p>
      </section>
      {rulesHit.length > 0 ? (
        <details className="rail-card fold" data-testid="rules-hit">
          <summary>{rail.redone(rulesHit.length)}</summary>
          <p className="quiet">{words.rulesHitIntro}</p>
          <ul className="redone-list">
            {rulesHit.map((hit, index) => (
              <li key={index}>{words.ruleHit(word(hit.rule), word(hit.code) || word(hit.tool), word(hit.message))}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
