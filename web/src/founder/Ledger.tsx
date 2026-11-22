/** The ledger (FND-5): each decision, its value, and a plain tag for where it came from. */
import { t } from "../strings";
import { decisionName, sourceTag, type LedgerLine } from "./logic";

export function Ledger({ ledger }: { ledger: LedgerLine[] }): JSX.Element {
  const words = t.founder.side;
  return (
    <section className="side-part" aria-labelledby="ledger-title" data-testid="ledger">
      <h2 id="ledger-title">{words.ledger}</h2>
      <p className="quiet">{ledger.length === 0 ? words.ledgerEmpty : words.ledgerIntro}</p>
      <ul className="records plain" aria-labelledby="ledger-title">
        {ledger.map((line) => (
          <li key={line.settles} data-testid="ledger-line" data-settles={line.settles} data-source={line.source}>
            <p className="row wrap">
              <span className="record-text">{decisionName(line.settles)}</span>
              <span className={`marker source-${line.source}`}>{sourceTag(line.source)}</span>
            </p>
            <p className="agent-text">{line.value}</p>
            {line.passage ? (
              <p className="quiet">
                {words.passage}: <q>{line.passage}</q>
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
