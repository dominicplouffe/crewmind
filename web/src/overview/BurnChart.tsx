/**
 * A burn-up chart of tokens used (GOV-1, PLN-5): the cumulative total as a step line, the budget
 * wall with its warning and wrap-up levels, and a dashed projection at the measured pace. Every
 * line is named in text, the time axis is labelled in the unit its span needs, and a table of the
 * points sits behind it for screen readers. `compact` is the side rail's small version: the same
 * lines, fewer labels.
 */
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { get } from "../api/client";
import { loadRuns } from "../crew/data";
import { compactNumber, fromNow, tokens } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { burn, story } from "../strings.overview";
import { burnPlan, burnSeries, niceTicks, pointAt, timeTicks, type BurnPlan, type BurnPoint } from "./burn";

interface Props {
  projectId: string;
  changes: number;
  compact?: boolean;
}

const MARGIN = { top: 14, right: 12, bottom: 24, left: 44 };
const TABLE_ROWS = 40;
/** A tick label closer than this to an edge is anchored to it instead of centred. */
const EDGE = 28;
const fullTime = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function useWidth<T extends HTMLElement>(fallback: number): [RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? fallback);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [fallback]);
  return [ref, width];
}

function stepPath(points: BurnPoint[], x: (at: number) => number, y: (total: number) => number): string {
  return points
    .map((point, index) => {
      const px = x(point.at).toFixed(1);
      const py = y(point.total).toFixed(1);
      return index === 0 ? `M${px},${py}` : `H${px}V${py}`;
    })
    .join("");
}

function Chart({
  plan,
  wall,
  warnAt,
  wrapupAt,
  width,
  height,
  label,
  compact,
}: {
  plan: BurnPlan;
  wall: number;
  warnAt: number;
  wrapupAt: number;
  width: number;
  height: number;
  label: string;
  compact: boolean;
}): JSX.Element {
  const [hover, setHover] = useState<number | null>(null);
  const inner = { width: Math.max(10, width - MARGIN.left - MARGIN.right), height: Math.max(10, height - MARGIN.top - MARGIN.bottom) };
  const x = (at: number): number => MARGIN.left + ((at - plan.xMin) / Math.max(1, plan.xMax - plan.xMin)) * inner.width;
  const y = (total: number): number => MARGIN.top + inner.height - (total / plan.yMax) * inner.height;
  const ticks = niceTicks(plan.yMax, height < 160 ? 2 : 4).filter((value) => value <= plan.yMax);
  const times = timeTicks(plan.xMin, plan.xMax, compact || width < 420 ? 3 : 5);
  const right = MARGIN.left + inner.width;
  const line = stepPath(plan.points, x, y);
  const area = `${line}V${y(0).toFixed(1)}H${x(plan.points[0]?.at ?? plan.xMin).toFixed(1)}Z`;
  const levels = [
    { key: "warn", value: warnAt, name: burn.legend.warn },
    { key: "wrapup", value: wrapupAt, name: burn.legend.wrapup },
  ].filter((level) => level.value > 0 && level.value <= plan.yMax);
  const hovered = hover === null ? null : pointAt(plan.points, hover);

  return (
    <div className="burn-plot">
      <svg width={width} height={height} role="img" aria-label={label} className="burn-svg">
        <g className="burn-grid" aria-hidden="true">
          {ticks.map((value) => (
            <g key={value}>
              <line x1={MARGIN.left} x2={MARGIN.left + inner.width} y1={y(value)} y2={y(value)} />
              <text x={MARGIN.left - 6} y={y(value)} dy="0.32em" textAnchor="end">
                {compactNumber(value)}
              </text>
            </g>
          ))}
          {times.map((tick) => {
            const at = x(tick.at);
            const anchor = at - MARGIN.left < EDGE ? "start" : right - at < EDGE ? "end" : "middle";
            return (
              <text key={tick.at} x={at} y={height - 6} textAnchor={anchor}>
                {tick.label}
              </text>
            );
          })}
        </g>

        {levels.map((level) => (
          <g key={level.key} className={`burn-level burn-${level.key}`} aria-hidden="true">
            <line x1={MARGIN.left} x2={MARGIN.left + inner.width} y1={y(level.value)} y2={y(level.value)} />
            {compact ? null : (
              <text x={MARGIN.left + inner.width} y={y(level.value) - 4} textAnchor="end">
                {level.name} · {compactNumber(level.value)}
              </text>
            )}
          </g>
        ))}
        {plan.wallVisible ? (
          <g className="burn-wall" aria-hidden="true">
            <line x1={MARGIN.left} x2={MARGIN.left + inner.width} y1={y(wall)} y2={y(wall)} />
            <text x={MARGIN.left + 2} y={y(wall) - 5}>
              {burn.legend.wall} · {compactNumber(wall)}
            </text>
          </g>
        ) : null}

        <path className="burn-area" d={area} aria-hidden="true" />
        <path className="burn-line" d={line} aria-hidden="true" />
        {plan.projection ? (
          <g className="burn-projection" aria-hidden="true">
            <line x1={x(plan.current.at)} y1={y(plan.current.total)} x2={x(plan.projection.to.at)} y2={y(plan.projection.to.total)} />
            {plan.projection.hitsWall ? <circle cx={x(plan.projection.to.at)} cy={y(plan.projection.to.total)} r={3.5} /> : null}
          </g>
        ) : null}
        <circle className="burn-now" cx={x(plan.current.at)} cy={y(plan.current.total)} r={4} aria-hidden="true" />
        <text
          className="burn-now-label"
          x={x(plan.current.at) - 8}
          y={y(plan.current.total) - 9}
          textAnchor="end"
          aria-hidden="true"
        >
          {compactNumber(plan.current.total)}
        </text>

        {hovered ? (
          <g className="burn-hover" aria-hidden="true">
            <line x1={x(hover ?? 0)} x2={x(hover ?? 0)} y1={MARGIN.top} y2={MARGIN.top + inner.height} />
            <circle cx={x(hover ?? 0)} cy={y(hovered.total)} r={4} />
          </g>
        ) : null}
        <rect
          className="burn-hit"
          x={MARGIN.left}
          y={MARGIN.top}
          width={inner.width}
          height={inner.height}
          onPointerMove={(event) => {
            const box = event.currentTarget.getBoundingClientRect();
            const share = (event.clientX - box.left) / Math.max(1, box.width);
            const at = plan.xMin + share * (plan.xMax - plan.xMin);
            setHover(Math.min(at, plan.current.at));
          }}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {hovered && hover !== null ? (
        <div
          className="burn-tip"
          style={{ left: Math.min(Math.max(x(hover), 70), width - 70), top: Math.max(0, y(hovered.total) - 44) }}
          aria-hidden="true"
        >
          <strong className="tabular">{tokens(hovered.total)}</strong>
          <span>{fullTime.format(hover)}</span>
        </div>
      ) : null}
    </div>
  );
}

export function BurnChart({ projectId, changes, compact = false }: Props): JSX.Element {
  const runs = useLoad(() => loadRuns(projectId), [projectId, changes]);
  const budget = useLoad(() => get("/v1/budget/show", { project_id: projectId }), [projectId, changes]);
  const planView = useLoad(() => get("/v1/plan/show", { project_id: projectId }), [projectId, changes]);
  const [ref, width] = useWidth<HTMLDivElement>(compact ? 320 : 640);
  const height = compact ? 132 : 220;

  const data = useMemo(() => {
    if (!runs.data || !budget.data) return null;
    const now = Date.now();
    const points = burnSeries(runs.data, budget.data.spent, now);
    const pace = planView.data?.pace;
    const plan = burnPlan({
      points,
      wall: budget.data.wall,
      burnRate: pace?.burn_rate ?? null,
      projectedAt: pace?.projected_at ?? null,
    });
    return { points, plan };
  }, [runs.data, budget.data, planView.data]);

  const error = runs.error ?? budget.error;
  let body: JSX.Element;
  if (error && !data) {
    body = (
      <div className="burn-error" role="alert">
        <p className="quiet">{story.sectionError}</p>
        <button
          type="button"
          className="button small"
          onClick={() => {
            runs.reload();
            budget.reload();
          }}
        >
          {story.retry}
        </button>
      </div>
    );
  } else if (!data || !budget.data) {
    body = <span className="skeleton burn-skeleton" style={{ height }} />;
  } else {
    body = (
      <BurnFigure
        data={data}
        budget={budget.data}
        pace={planView.data?.pace.burn_rate ?? null}
        width={width}
        height={height}
        compact={compact}
      />
    );
  }
  return (
    <div className={`burn${compact ? " compact" : ""}`} ref={ref}>
      {body}
    </div>
  );
}

function BurnFigure({
  data,
  budget,
  pace,
  width,
  height,
  compact,
}: {
  data: { points: BurnPoint[]; plan: BurnPlan | null };
  budget: { spent: number; wall: number; warn_at: number; wrapup_at: number };
  pace: number | null;
  width: number;
  height: number;
  compact: boolean;
}): JSX.Element {
  const { plan, points } = data;
  const wall = budget.wall;
  const paceText = pace ? burn.pace(compactNumber(pace)) : burn.noPace;
  const wallText =
    plan?.projection?.hitsWall && plan.projection ? burn.reachesWall(fromNow(new Date(plan.projection.to.at).toISOString())) : "";
  const label = burn.label(tokens(budget.spent), tokens(wall), `${paceText}${wallText ? `, ${wallText}` : ""}.`);

  return (
    <figure className="burn-figure">
      {plan ? (
        <>
          {!plan.wallVisible ? (
            <p className="burn-far">
              <span aria-hidden="true">↑ </span>
              {burn.wallAbove(compactNumber(wall))}
            </p>
          ) : null}
          <Chart
            plan={plan}
            wall={wall}
            warnAt={budget.warn_at}
            wrapupAt={budget.wrapup_at}
            width={width}
            height={height}
            label={label}
            compact={compact}
          />
          <figcaption className={compact ? "visually-hidden" : "burn-legend"}>
            <span className="burn-key key-used">{burn.legend.used}</span>
            {plan.projection ? <span className="burn-key key-projection">{burn.legend.projection}</span> : null}
            {plan.wallVisible ? <span className="burn-key key-wall">{burn.legend.wall}</span> : null}
            {wallText ? <span className="quiet">{wallText}</span> : null}
          </figcaption>
          <table className="visually-hidden">
            <caption>{burn.tableCaption}</caption>
            <thead>
              <tr>
                <th scope="col">{burn.time}</th>
                <th scope="col">{burn.total}</th>
              </tr>
            </thead>
            <tbody>
              {points.slice(-TABLE_ROWS).map((point, index) => (
                <tr key={`${point.at}-${index}`}>
                  <td>{fullTime.format(point.at)}</td>
                  <td>{tokens(point.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p className="burn-empty quiet">{burn.noData}</p>
      )}
    </figure>
  );
}
