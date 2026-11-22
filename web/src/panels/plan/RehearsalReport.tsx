/** A rehearsal report (RHS-3) in plain sections: the verdict, the walk, the waits, and what the drill found. */
import type { Schemas } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { t } from "../../strings";
import { AgentText } from "../board/parts";
import { Section } from "./parts";

export type Report = Schemas["RehearsalReport"];

function Lines({ lines, empty, testId }: { lines: string[]; empty?: string; testId?: string }): JSX.Element | null {
  if (lines.length === 0) return empty ? <p className="quiet">{empty}</p> : null;
  return (
    <ul data-testid={testId}>
      {lines.map((line, index) => (
        <li key={index}>
          <AgentText text={line} />
        </li>
      ))}
    </ul>
  );
}

const seconds = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

export function RehearsalReport({ report }: { report: Report }): JSX.Element {
  const words = t.founder.rehearse;
  const { estimate } = report;
  return (
    <div data-testid="rehearsal-report">
      <Section title={words.verdict}>
        <p className="record-text" data-testid="rehearsal-verdict">
          {report.verdict}
        </p>
        <p className={report.ok ? "marker grade-present" : "marker grade-missing"}>{report.ok ? words.ok : words.notOk}</p>
      </Section>
      <Section title={words.walk}>
        <ol data-testid="rehearsal-walk">
          {report.walk.map((step, index) => (
            <li key={index} data-happened={step.happened}>
              {step.what}{" "}
              <span className="quiet">
                {step.happened && step.after_seconds !== null && step.after_seconds !== undefined
                  ? words.stepAt(seconds.format(step.after_seconds))
                  : words.stepMissed}
              </span>
            </li>
          ))}
        </ol>
      </Section>
      <Section title={words.waited}>
        <Lines
          lines={report.waited_for_the_chairman.map((wait) => `${wait.kind}: ${words.times(wait.times)}`)}
          empty={words.waitedNone}
        />
      </Section>
      <Section title={words.setup}>
        <Lines lines={report.setup_missing ?? []} empty={words.setupNone} testId="rehearsal-setup" />
      </Section>
      <Section title={words.staffing}>
        <Lines lines={report.staffing ?? []} empty={words.staffingNone} />
      </Section>
      <Section title={words.rules}>
        {report.rules_hit && report.rules_hit.length > 0 ? (
          <ul>
            {report.rules_hit.map((hit, index) => (
              <li key={index}>
                {words.rule(hit.rule, hit.times)}
                <br />
                <span className="quiet">{hit.message}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="quiet">{words.rulesNone}</p>
        )}
      </Section>
      <Section title={words.clock}>
        <Lines lines={report.clock ?? []} />
      </Section>
      <Section title={words.estimate}>
        <p>
          {words.runs(estimate.runs_to_first_close)}
          {estimate.tokens_to_first_close !== null && estimate.tokens_to_first_close !== undefined
            ? `, ${words.tokens(formatNumber(estimate.tokens_to_first_close))}`
            : ""}
        </p>
        <p className="quiet">{estimate.basis}</p>
      </Section>
      <Section title={words.shape}>
        <dl className="pairs">
          <div>
            <dt>{words.parallel}</dt>
            <dd>
              <AgentText text={report.parallelism} />
            </dd>
          </div>
          <div>
            <dt>{words.chain}</dt>
            <dd>
              <AgentText text={report.longest_chain} />
            </dd>
          </div>
          <div>
            <dt>{words.duration}</dt>
            <dd>
              <AgentText text={report.projected_duration} />
            </dd>
          </div>
        </dl>
      </Section>
      <Section title={words.notExercised}>
        <Lines lines={report.not_exercised ?? []} />
      </Section>
      <p className="note">{report.note}</p>
    </div>
  );
}
