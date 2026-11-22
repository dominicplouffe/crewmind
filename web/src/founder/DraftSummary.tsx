/** The proposed project: its name, type, goal, teams and the settings it changes, and the rehearsal verdict. */
import { Markdown, Pre } from "../components/common";
import { formatDateTime, formatNumber, formatValue } from "../lib/format";
import { t } from "../strings";
import type { DraftSummary as Summary } from "./logic";

interface Props {
  draft: Summary | null;
  /** The verdict of the rehearsal of this draft, when it has been rehearsed. */
  rehearsal: string | null;
  /** Steps of the Founder that a rule refused. */
  rulesHit: Record<string, unknown>[];
}

const word = (value: unknown): string => (typeof value === "string" ? value : "");

export function DraftSummary({ draft, rehearsal, rulesHit }: Props): JSX.Element {
  const words = t.founder.side;
  const types: Record<string, string> = t.projects.types;
  return (
    <>
      <section className="side-part" aria-labelledby="draft-title" data-testid="draft">
        <h2 id="draft-title">{words.draft}</h2>
        {draft ? (
          <>
            <dl className="pairs">
              <div>
                <dt>{words.name}</dt>
                <dd data-testid="draft-name">{draft.name}</dd>
              </div>
              <div>
                <dt>{words.type}</dt>
                <dd>{types[draft.type] ?? draft.type}</dd>
              </div>
              {draft.quality ? (
                <div>
                  <dt>{words.quality}</dt>
                  <dd>{draft.quality}</dd>
                </div>
              ) : null}
              {draft.budgetTokens !== null ? (
                <div>
                  <dt>{words.budget}</dt>
                  <dd>{words.budgetTokens(formatNumber(draft.budgetTokens))}</dd>
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
              {draft.payingCredential ? (
                <div>
                  <dt>{words.pays}</dt>
                  <dd>{draft.payingCredential}</dd>
                </div>
              ) : null}
            </dl>
            <h3 className="group-title">{words.goal}</h3>
            <Markdown source={draft.goal} className="draft-goal" />
            <h3 className="group-title">{words.teams}</h3>
            {draft.teams.length === 0 ? <p className="quiet">{words.noTeams}</p> : null}
            {draft.teams.length > 0 ? (
              <ul>
                {draft.teams.map((team) => (
                  <li key={team.name} data-testid="draft-team">
                    {words.team(team.name, team.role)}: {team.members.join(", ")}
                  </li>
                ))}
              </ul>
            ) : null}
            <h3 className="group-title">{words.settings}</h3>
            {draft.settings.length === 0 ? <p className="quiet">{words.noSettings}</p> : null}
            {draft.settings.length > 0 ? (
              <dl className="pairs">
                {draft.settings.map(([name, value]) => (
                  <div key={name}>
                    <dt>{name}</dt>
                    <dd>{typeof value === "object" && value !== null ? <Pre>{formatValue(value)}</Pre> : formatValue(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </>
        ) : (
          <p className="quiet">{words.draftEmpty}</p>
        )}
      </section>
      <section className="side-part" aria-labelledby="rehearsal-title" data-testid="draft-rehearsal">
        <h2 id="rehearsal-title">{words.rehearsal}</h2>
        <p className={rehearsal ? undefined : "quiet"}>{rehearsal ?? words.rehearsalNone}</p>
      </section>
      {rulesHit.length > 0 ? (
        <section className="side-part" aria-labelledby="rules-hit-title" data-testid="rules-hit">
          <h2 id="rules-hit-title">{words.rulesHit}</h2>
          <p className="quiet">{words.rulesHitIntro}</p>
          <ul>
            {rulesHit.map((hit, index) => (
              <li key={index}>{words.ruleHit(word(hit.rule), word(hit.code) || word(hit.tool))}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
