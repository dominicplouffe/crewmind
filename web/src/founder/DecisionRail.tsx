/**
 * Every decision a project rests on and where each one stands (FND-4, FND-5): what is decided,
 * with its value and where it came from (your words, your answer, or assumed), and what is still to
 * decide, the one being asked now marked. Settled first, because that is what the draft says.
 */
import { Check, Circle, CircleDot } from "lucide-react";
import { t } from "../strings";
import { decisionName, settledCount, sourceTag, type Decision, type LedgerLine } from "./logic";

interface Props {
  decisions: Decision[];
  /** The whole ledger: it also holds what was settled about passages of a document. */
  ledger: LedgerLine[];
}

function Settled({ settles, value, source }: { settles: string; value: string; source: string | null }): JSX.Element {
  return (
    <li className="decision decision-settled" data-testid="ledger-line" data-settles={settles} data-source={source ?? undefined}>
      <Check size={16} aria-hidden="true" className="decision-icon" />
      <div className="decision-body">
        <p className="decision-name">
          <span>{decisionName(settles)}</span>
          {source ? <span className={`badge source-${source}`}>{sourceTag(source)}</span> : null}
        </p>
        <p className="decision-value">{value}</p>
      </div>
    </li>
  );
}

export function DecisionRail({ decisions, ledger }: Props): JSX.Element {
  const words = t.founder.decide;
  const settled = decisions.filter((decision) => decision.state === "settled");
  const open = decisions.filter((decision) => decision.state !== "settled");
  const keys = new Set(decisions.map((decision) => decision.key));
  const passages = ledger.filter((line) => !keys.has(line.settles));
  return (
    <section className="rail-card" aria-labelledby="decisions-title" data-testid="ledger">
      <header className="rail-head">
        <h2 id="decisions-title">{words.title}</h2>
        <span className="rail-count" data-testid="decisions-progress">
          {words.progress(settledCount(decisions), decisions.length)}
        </span>
      </header>
      {settled.length === 0 ? <p className="quiet small">{words.nothingDecided}</p> : null}
      {settled.length > 0 ? (
        <>
          <h3 className="rail-subtitle">{words.decided}</h3>
          <ul className="decision-list">
            {settled.map((decision) => (
              <Settled key={decision.key} settles={decision.key} value={decision.value ?? ""} source={decision.source ?? null} />
            ))}
          </ul>
        </>
      ) : null}
      {open.length > 0 ? (
        <>
          <h3 className="rail-subtitle">{words.toDecide}</h3>
          <ul className="decision-open-list">
            {open.map((decision) => {
              const asked = decision.state === "asked";
              const Icon = asked ? CircleDot : Circle;
              return (
                <li
                  key={decision.key}
                  className={`decision-open decision-${decision.state}`}
                  data-testid="decision-open"
                  data-settles={decision.key}
                >
                  <Icon size={14} aria-hidden="true" className="decision-icon" />
                  <span>{decisionName(decision.key)}</span>
                  {asked ? <span className="badge asked-now">{words.askedNow}</span> : null}
                  <span className="visually-hidden"> ({words.state[decision.state] ?? decision.state})</span>
                </li>
              );
            })}
          </ul>
        </>
      ) : decisions.length > 0 ? (
        <p className="quiet small">{words.allDecided}</p>
      ) : null}
      {passages.length > 0 ? (
        <>
          <h3 className="rail-subtitle">{words.fromDocument}</h3>
          <ul className="decision-list">
            {passages.map((line) => (
              <Settled key={line.settles} settles={line.settles} value={line.value} source={line.source} />
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
