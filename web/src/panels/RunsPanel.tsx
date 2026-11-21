/** Runs: the list, and one run's trace (what it was told, each model call and tool call). */
import { get } from "../api/client";
import { Empty, ErrorNote, Loading, Pre } from "../components/common";
import { formatDateTime, formatNumber, formatValue } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";

interface Props {
  projectId: string;
  changes: number;
  runId: string | undefined;
  onSelect(runId: string | undefined): void;
}

function Trace({ projectId, runId, onBack }: { projectId: string; runId: string; onBack(): void }): JSX.Element {
  const trace = useLoad(() => get("/v1/runs/trace", { project_id: projectId, run_id: runId }), [projectId, runId]);
  const data = trace.data;
  return (
    <div data-testid="run-trace">
      <button type="button" className="link" onClick={onBack}>
        {t.runs.back}
      </button>
      <ErrorNote error={trace.error} />
      {trace.loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <h3>{t.runs.traceTitle(data.seat, data.kind)}</h3>
          <dl className="pairs">
            <div>
              <dt>{t.runs.state}</dt>
              <dd>{data.end_detail ? `${data.state}: ${data.end_detail}` : data.state}</dd>
            </div>
            <div>
              <dt>{t.runs.why}</dt>
              <dd>{data.reasons.join("; ")}</dd>
            </div>
            <div>
              <dt>{t.runs.model}</dt>
              <dd>{data.model ?? t.runs.none}</dd>
            </div>
            <div>
              <dt>{t.runs.tokens}</dt>
              <dd>{formatNumber(data.tokens_counted)}</dd>
            </div>
          </dl>
          <h3>{t.runs.steps}</h3>
          {data.steps.length === 0 ? <p className="quiet">{t.runs.noSteps}</p> : null}
          <ol className="steps">
            {data.steps.map((step, index) => {
              const { kind, at, ...rest } = step as { kind?: unknown; at?: unknown } & Record<string, unknown>;
              return (
                <li key={index}>
                  <p>
                    <strong>{formatValue(kind)}</strong>{" "}
                    <span className="quiet">{typeof at === "string" ? formatDateTime(at) : ""}</span>
                  </p>
                  <Pre>{formatValue(rest)}</Pre>
                </li>
              );
            })}
          </ol>
          {data.system_prompt ? (
            <details>
              <summary>{t.runs.systemPrompt}</summary>
              <Pre>{data.system_prompt}</Pre>
            </details>
          ) : null}
          {data.context_pack ? (
            <details>
              <summary>{t.runs.context}</summary>
              <Pre>{data.context_pack}</Pre>
            </details>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function RunsPanel({ projectId, changes, runId, onSelect }: Props): JSX.Element {
  const runs = useLoad(() => get("/v1/runs/list", { project_id: projectId, limit: 100 }), [projectId, changes]);
  if (runId) return <Trace projectId={projectId} runId={runId} onBack={() => onSelect(undefined)} />;
  const items = runs.data?.items ?? [];
  return (
    <>
      <ErrorNote error={runs.error} />
      {runs.loading && !runs.data ? <Loading /> : null}
      {runs.data && items.length === 0 ? <Empty title={t.runs.emptyTitle} next={t.runs.emptyNext} /> : null}
      <ul className="cards plain">
        {items.map((run) => (
          <li key={run.run_id} className="mini-card">
            <button type="button" className="link strong" onClick={() => onSelect(run.run_id)}>
              {t.runs.line(run.seat, run.kind, run.state)}
            </button>
            <p className="quiet">{run.reasons.join("; ")}</p>
            <p className="quiet">
              {t.runs.meta(formatDateTime(run.queued_at), formatNumber(run.tokens_counted), run.model ?? t.runs.none)}
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}
