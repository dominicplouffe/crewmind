/** Pinned memory: exactly what one agent is given at the start of every run, and how full it is. */
import { useId, useState } from "react";
import { get, type Seat } from "../../api/client";
import { ErrorNote, Loading, Markdown } from "../../components/common";
import { formatNumber } from "../../lib/format";
import { meter } from "../../lib/meter";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import type { TabProps } from "./parts";

/** "2 corrections in 40 replies (score 5)", or "no replies yet" while the score is unknown. */
export function listeningLine(seat: Pick<Seat, "replies" | "corrections" | "listening_score">): string {
  if (seat.listening_score === null || seat.listening_score === undefined) return t.listening.noReplies;
  return t.listening.score(seat.corrections ?? 0, seat.replies ?? 0, formatNumber(seat.listening_score));
}

function SizeMeter({ name, used, cap }: { name: string; used: number; cap: number }): JSX.Element {
  const id = useId();
  const size = meter(used, cap);
  return (
    <div className="meter" data-testid="meter">
      <p id={id}>{t.memory.pinned.meter(name, formatNumber(used), formatNumber(cap))}</p>
      <progress max={100} value={size.percent} aria-labelledby={id} />
      {size.over ? (
        <p className="note note-error" role="status">
          {t.memory.pinned.over(name, formatNumber(size.overBy))}
        </p>
      ) : null}
    </div>
  );
}

export function PinnedTab({ projectId, changes }: TabProps): JSX.Element {
  const [chosen, setChosen] = useState<string | null>(null);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, changes]);
  const pinned = useLoad(
    () => get("/v1/memory/pinned", { project_id: projectId, seat: chosen ?? undefined }),
    [projectId, chosen, changes],
  );
  const id = useId();
  const data = pinned.data;
  const seats = roster.data?.seats ?? [];
  // Until the person picks one, the server chooses (the CEO) and says which it chose.
  const seatName = chosen ?? data?.seat ?? "";
  const seat = seats.find((item) => item.name === seatName);

  return (
    <>
      <ErrorNote error={roster.error} />
      <div className="field">
        <label htmlFor={id}>{t.memory.pinned.agent}</label>
        <select id={id} value={seatName} onChange={(event) => setChosen(event.target.value)}>
          {seats.length === 0 && seatName ? <option value={seatName}>{seatName}</option> : null}
          {seats.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name === item.role ? item.name : `${item.name} · ${item.role}`}
            </option>
          ))}
        </select>
      </div>
      {seat ? (
        <p className="quiet" data-testid="listening-score" title={t.listening.scoreHint}>
          {t.memory.pinned.listening}: {listeningLine(seat)}
        </p>
      ) : null}
      <ErrorNote error={pinned.error} />
      {pinned.loading && !data ? <Loading /> : null}
      {data && !pinned.error ? (
        <>
          <SizeMeter name={t.memory.pinned.meters.project} used={data.project_tokens} cap={data.project_cap} />
          <SizeMeter name={t.memory.pinned.meters.agent} used={data.agent_tokens} cap={data.agent_cap} />
          <p className="quiet">{t.memory.pinned.intro(data.seat)}</p>
          <section className="pinned-text" aria-label={t.memory.pinned.textLabel(data.seat)} data-testid="pinned-text">
            <Markdown source={data.text} />
          </section>
        </>
      ) : null}
    </>
  );
}
