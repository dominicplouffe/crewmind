/**
 * Every decision a project rests on, in the order they are asked, and where each one stands
 * (FND-4, FND-5): settled with its value and where it came from, being asked now, or not asked
 * yet. It stays in view while the person drafts, so what is left is never a guess.
 */
import { Check, Circle, CircleDot } from "lucide-react";
import { t } from "../strings";
import { decisionName, settledCount, sourceTag, type Decision, type LedgerLine } from "./logic";

interface Props {
  decisions: Decision[];
  /** The whole ledger: it also holds what was settled about passages of a document. */
  ledger: LedgerLine[];
}

const ICONS = { settled: Check, asked: CircleDot, open: Circle };

export function DecisionRail({ decisions, ledger }: Props): JSX.Element {
  const words = t.founder.decide;
  const settled = settledCount(decisions);
  const keys = new Set(decisions.map((decision) => decision.key));
  const passages = ledger.filter((line) => !keys.has(line.settles));
  return (
    <section className="rail-card" aria-labelledby="decisions-title" data-testid="ledger">
      <header className="rail-head">
        <h2 id="decisions-title">{words.title}</h2>
        <span className="rail-count" data-testid="decisions-progress">
          {words.progress(settled, decisions.length)}
        </span>
      </header>
      <progress className="decide-meter" max={decisions.length} value={settled} aria-label={words.progressLabel} />
      <ol className="decision-list">
        {decisions.map((decision) => {
          const Icon = ICONS[decision.state as keyof typeof ICONS] ?? Circle;
          return (
            <li
              key={decision.key}
              className={`decision decision-${decision.state}`}
              data-testid={decision.state === "settled" ? "ledger-line" : "decision-open"}
              data-settles={decision.key}
              data-source={decision.source ?? undefined}
            >
              <Icon size={16} aria-hidden="true" className="decision-icon" />
              <div className="decision-body">
                <p className="decision-name">
                  <span>{decisionName(decision.key)}</span>
                  {decision.source ? (
                    <span className={`badge source-${decision.source}`}>{sourceTag(decision.source)}</span>
                  ) : null}
                  <span className="visually-hidden"> {words.state[decision.state] ?? decision.state}</span>
                </p>
                {decision.state === "settled" ? (
                  <p className="decision-value">{decision.value}</p>
                ) : (
                  <p className="decision-note">{decision.state === "asked" ? words.askedNow : words.notYet}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {passages.length > 0 ? (
        <>
          <h3 className="rail-subtitle">{words.fromDocument}</h3>
          <ul className="decision-list">
            {passages.map((line) => (
              <li
                key={line.settles}
                className="decision decision-settled"
                data-testid="ledger-line"
                data-settles={line.settles}
                data-source={line.source}
              >
                <Check size={16} aria-hidden="true" className="decision-icon" />
                <div className="decision-body">
                  <p className="decision-name">
                    <span>{decisionName(line.settles)}</span>
                    <span className={`badge source-${line.source}`}>{sourceTag(line.source)}</span>
                  </p>
                  <p className="decision-value">{line.value}</p>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
