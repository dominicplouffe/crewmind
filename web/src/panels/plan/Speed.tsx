/** Speed: how long the first task, the first deliverable and the finish took, and where the time went. */
import { t } from "../../strings";
import { durationText, type TimeRow } from "./logic";

const time = (seconds: number | null | undefined): string =>
  seconds === null || seconds === undefined ? t.plan.finish.speed.notYet : durationText(seconds);

interface Props {
  toFirstTask: number | null | undefined;
  toFirstDeliverable: number | null | undefined;
  toDone: number | null | undefined;
  where: TimeRow[];
}

/** The three times and where the time went, one labelled bar for each place. */
export function TimeReport({ toFirstTask, toFirstDeliverable, toDone, where }: Props): JSX.Element {
  const words = t.plan.finish.speed;
  return (
    <>
      <dl className="pairs">
        <div>
          <dt>{words.firstTask}</dt>
          <dd data-testid="time-first-task">{time(toFirstTask)}</dd>
        </div>
        <div>
          <dt>{words.firstDeliverable}</dt>
          <dd>{time(toFirstDeliverable)}</dd>
        </div>
        <div>
          <dt>{words.done}</dt>
          <dd>{time(toDone)}</dd>
        </div>
      </dl>
      <p className="quiet">{words.where}</p>
      {where.length === 0 ? <p className="quiet">{words.whereNone}</p> : null}
      <ul className="plain time-rows" aria-label={words.whereLabel}>
        {where.map((row) => (
          <li key={row.name} data-testid="time-row">
            <span className="time-name">{row.name}</span>
            <span className="num">{durationText(row.seconds)}</span>
            <progress max={100} value={row.percent} aria-label={words.share(row.name, row.percent)} />
          </li>
        ))}
      </ul>
    </>
  );
}
