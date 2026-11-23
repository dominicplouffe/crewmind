/** Pinned memory: exactly what one agent is given at the start of every run, and how full it is. */
import { useId, useState } from "react";
import { get, type Seat } from "../../api/client";
import { ErrorNote, Markdown } from "../../components/common";
import { Loading } from "../kit";
import { formatNumber } from "../../lib/format";
import { meter } from "../../lib/meter";
import { useLoad } from "../../lib/useLoad";
import { Meter } from "../../ui/Progress";
import { t } from "../../strings";
import type { TabProps } from "./parts";
import { roleLabel, useAgentName } from "../../crew/names";

/** "2 corrections in 40 replies (score 5)", or "no replies yet" while the score is unknown. */
export function listeningLine(seat: Pick<Seat, "replies" | "corrections" | "listening_score">): string {
  if (seat.listening_score === null || seat.listening_score === undefined) return t.listening.noReplies;
  return t.listening.score(seat.corrections ?? 0, seat.replies ?? 0, formatNumber(seat.listening_score));
}

function SizeMeter({ name, used, cap }: { name: string; used: number; cap: number }): JSX.Element {
  const size = meter(used, cap);
  const line = t.memory.pinned.meter(name, formatNumber(used), formatNumber(cap));
  return (
    <div className="size-meter" data-testid="meter">
      <p className="size-meter-line">
        <span>{line}</span>
        <span className="quiet tabular">{size.percent}%</span>
      </p>
      <Meter value={Math.min(used, cap)} max={cap} label={line} tone={size.over ? "danger" : "accent"} />
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
  const nameOf = useAgentName();

  return (
    <>
      <ErrorNote error={roster.error} />
      <div className="field panel-field">
        <label htmlFor={id}>{t.memory.pinned.agent}</label>
        <select id={id} value={seatName} onChange={(event) => setChosen(event.target.value)}>
          {seats.length === 0 && seatName ? <option value={seatName}>{seatName}</option> : null}
          {seats.map((item) => (
            <option key={item.name} value={item.name}>
              {`${item.display_name || item.name} · ${roleLabel(item)}`}
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
          <p className="quiet">{t.memory.pinned.intro(nameOf(data.seat).name)}</p>
          <section className="pinned-text" aria-label={t.memory.pinned.textLabel(nameOf(data.seat).name)} data-testid="pinned-text">
            <Markdown source={data.text} />
          </section>
        </>
      ) : null}
    </>
  );
}
