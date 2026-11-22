/** The receipt of a completed project: what each requirement took, the tokens, the time and the commitment. */
import { formatDateTime, formatNumber } from "../../lib/format";
import { t } from "../../strings";
import { durationText, type ReceiptView } from "./logic";
import { Section } from "./parts";
import { TimeReport } from "./Speed";

const count = (value: number | null): string => (value === null ? "" : formatNumber(value));

export function Receipt({ receipt }: { receipt: ReceiptView }): JSX.Element {
  const words = t.plan.finish.receipt;
  const cycleWords = t.plan.scope.cycles;
  const card = receipt.finalScorecard;
  return (
    <Section title={words.title} testId="receipt">
      {receipt.requirements.length > 0 ? (
        <div className="table-scroll">
          <table className="grid">
            <caption>{words.requirements}</caption>
            <thead>
              <tr>
                <th scope="col">{words.requirement}</th>
                <th scope="col">{words.state}</th>
                <th scope="col" className="num">{words.estimate}</th>
                <th scope="col" className="num">{words.actual}</th>
                <th scope="col" className="num">{words.tokens}</th>
              </tr>
            </thead>
            <tbody>
              {receipt.requirements.map((row) => (
                <tr key={row.id}>
                  <th scope="row">
                    {row.id}. {row.text}
                  </th>
                  <td>{row.state}</td>
                  <td className="num">{count(row.estimateRuns)}</td>
                  <td className="num">{count(row.actualRuns)}</td>
                  <td className="num">{count(row.actualTokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {receipt.tokens.length > 0 ? (
        <table className="grid">
          <caption>{words.byKind}</caption>
          <thead>
            <tr>
              <th scope="col">{words.kind}</th>
              <th scope="col" className="num">{words.tokens}</th>
            </tr>
          </thead>
          <tbody>
            {receipt.tokens.map(([kind, tokens]) => (
              <tr key={kind}>
                <th scope="row">{words.kinds[kind] ?? kind.replace(/_/g, " ")}</th>
                <td className="num">{formatNumber(tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <dl className="pairs">
        {receipt.reserveDrawn !== null ? (
          <div>
            <dt>{words.reserveDrawn}</dt>
            <dd>{t.plan.tokens(formatNumber(receipt.reserveDrawn))}</dd>
          </div>
        ) : null}
        {receipt.wallClockSeconds !== null ? (
          <div>
            <dt>{words.wallClock}</dt>
            <dd data-testid="receipt-wall-clock">{durationText(receipt.wallClockSeconds)}</dd>
          </div>
        ) : null}
        <div>
          <dt>{words.commitment}</dt>
          <dd>
            {receipt.commitment
              ? words.commitmentLine(
                  receipt.commitment.kept,
                  receipt.commitment.date ? formatDateTime(receipt.commitment.date) : t.plan.unknown,
                  receipt.commitment.resets,
                  receipt.commitment.state,
                )
              : words.noCommitment}
          </dd>
        </div>
      </dl>
      {receipt.time ? (
        <TimeReport
          toFirstTask={receipt.time.toFirstTask}
          toFirstDeliverable={receipt.time.toFirstDeliverable}
          toDone={receipt.time.toDone}
          where={receipt.time.where}
        />
      ) : null}
      {receipt.bets.length > 0 ? (
        <>
          <p className="quiet">{words.bets}</p>
          <ul aria-label={words.bets}>
            {receipt.bets.map((bet) => (
              <li key={bet.id}>
                {words.bet(bet.id, bet.state)}. {bet.statement}
                {bet.finding ? ` (${t.plan.scope.bets.finding(bet.finding)})` : ""}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {receipt.findingsReport ? <p>{words.findingsReport(receipt.findingsReport)}</p> : null}
      {receipt.cycles.length > 0 ? (
        <>
          <p className="quiet">{words.cycles}</p>
          <ul aria-label={words.cycles}>
            {receipt.cycles.map((cycle) => (
              <li key={cycle.number}>{words.cycle(cycle.number, cycle.state)}</li>
            ))}
          </ul>
        </>
      ) : null}
      {card ? (
        <p>
          <span className="quiet">{words.finalScorecard}: </span>
          {cycleWords.scorecard(card.recurringMet, card.recurringTotal, card.workRuns, formatNumber(card.tokens))}
        </p>
      ) : null}
    </Section>
  );
}
