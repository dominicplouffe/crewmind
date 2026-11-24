/**
 * Runs (EXE, OBS): each run as a sentence ("CEO worked on a directive · finished 4 min ago ·
 * 12.4K tokens"), and one run's trace (what it was told, each model call and tool call). The raw
 * kind, state and reasons stay one click away under "Technical details".
 */
import { ChevronLeft, ChevronRight, Cpu } from "lucide-react";
import { get } from "../api/client";
import { ErrorNote, Pre } from "../components/common";
import { formatDateTime, formatNumber, formatValue } from "../lib/format";
import { tokens } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";
import { AgentAvatar, useAgentName } from "../squad/names";
import { Pill } from "../ui/Status";
import { Empty, Loading } from "./kit";
import { aboutWords, runSentence, runStateWords, runTone, type RunLike } from "./runWords";

interface Props {
  projectId: string;
  changes: number;
  runId: string | undefined;
  onSelect(runId: string | undefined): void;
}

interface Technical extends RunLike {
  run_id: string;
  attempt: number;
  model?: string | null;
  provider?: string | null;
}

/** The server's own values for a run, for whoever needs them. */
function TechnicalDetails({ run }: { run: Technical }): JSX.Element {
  const words = t.runs.fields;
  const rows: [string, string][] = [
    [words.id, run.run_id],
    [words.kind, run.kind],
    [words.state, run.state],
    [words.reasons, run.reasons.join("; ") || t.runs.none],
    [words.model, run.model ? `${run.model}${run.provider ? ` (${run.provider})` : ""}` : t.runs.none],
    [words.attempt, String(run.attempt)],
    [words.queued, formatDateTime(run.queued_at)],
    [words.started, run.started_at ? formatDateTime(run.started_at) : t.runs.none],
    [words.ended, run.ended_at ? formatDateTime(run.ended_at) : t.runs.none],
  ];
  return (
    <details className="technical">
      <summary>
        {t.runs.technical}
        <span className="visually-hidden"> {t.runs.technicalOf(run.seat)}</span>
      </summary>
      <dl className="pairs">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="mono">{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function Trace({ projectId, runId, onBack }: { projectId: string; runId: string; onBack(): void }): JSX.Element {
  const trace = useLoad(() => get("/v1/runs/trace", { project_id: projectId, run_id: runId }), [projectId, runId]);
  const data = trace.data;
  const nameOf = useAgentName();
  return (
    <div data-testid="run-trace" className="run-trace">
      <button type="button" className="button small ghost back-button" onClick={onBack}>
        <ChevronLeft size={16} aria-hidden="true" />
        {t.runs.back}
      </button>
      <ErrorNote error={trace.error} />
      {trace.loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <header className="trace-head">
            <AgentAvatar seat={data.seat} size="lg" />
            <div>
              <h3 className="trace-title">{runSentence(data, nameOf(data.seat).name)}</h3>
              <p className="quiet">
                <Pill tone={runTone(data.state)}>{runStateWords(data)}</Pill> · {tokens(data.tokens_counted)}
              </p>
            </div>
          </header>
          <dl className="pairs">
            <div>
              <dt>{t.runs.state}</dt>
              <dd>{data.end_detail ? `${runStateWords(data)}: ${data.end_detail}` : runStateWords(data)}</dd>
            </div>
            <div>
              <dt>{t.runs.why}</dt>
              <dd>{aboutWords(data.reasons) || t.runs.none}</dd>
            </div>
            <div>
              <dt>{t.runs.model}</dt>
              <dd>{data.model ? t.models.runsOn(data.model, data.provider ?? "") : t.runs.none}</dd>
            </div>
            <div>
              <dt>{t.runs.tokens}</dt>
              <dd className="tabular">{formatNumber(data.tokens_counted)}</dd>
            </div>
          </dl>
          <TechnicalDetails run={data} />
          <h3 className="group-title">{t.runs.steps}</h3>
          {data.steps.length === 0 ? <p className="quiet">{t.runs.noSteps}</p> : null}
          <ol className="steps">
            {data.steps.map((step, index) => {
              const { kind, at, ...rest } = step as { kind?: unknown; at?: unknown } & Record<string, unknown>;
              return (
                <li key={index}>
                  <p className="step-head">
                    <span className="badge">{formatValue(kind)}</span>
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
  const nameOf = useAgentName();
  if (runId) return <Trace projectId={projectId} runId={runId} onBack={() => onSelect(undefined)} />;
  const items = runs.data?.items ?? [];
  return (
    <>
      <ErrorNote error={runs.error} />
      {runs.loading && !runs.data ? <Loading lines={6} /> : null}
      {runs.data && items.length === 0 ? <Empty icon={Cpu} title={t.runs.emptyTitle} next={t.runs.emptyNext} /> : null}
      <ul className="rows plain">
        {items.map((run) => (
          <li key={run.run_id} className="run-row">
            <AgentAvatar seat={run.seat} size="sm" />
            <div className="row-main">
              <button type="button" className="row-title" onClick={() => onSelect(run.run_id)}>
                {runSentence(run, nameOf(run.seat).name)}
                <ChevronRight size={16} aria-hidden="true" className="row-chevron" />
              </button>
              <p className="row-meta">
                <Pill tone={runTone(run.state)}>{runStateWords(run)}</Pill>
                <span className="tabular">{tokens(run.tokens_counted)}</span>
                {run.model ? <span>{run.model}</span> : null}
              </p>
              <TechnicalDetails run={run} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
