/** Audit: closes drawn at random for the chairman to check. Each sample is judged once. */
import { useState } from "react";
import { get, post } from "../../api/client";
import { Empty, ErrorNote, Loading } from "../../components/common";
import { formatDateTime } from "../../lib/format";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { TextForm, useAct } from "../memory/parts";
import { AgentText, Bar, CheckLabel, type BoardTabProps } from "./parts";

interface Props extends BoardTabProps {
  onChanged(): void;
}

export function AuditTab({ projectId, changes, onChanged }: Props): JSX.Element {
  const audits = useLoad(() => get("/v1/audits/list", { project_id: projectId }), [projectId, changes]);
  const [failing, setFailing] = useState<number | null>(null);
  const act = useAct(() => {
    audits.reload();
    onChanged();
  });
  const data = audits.data;
  const items = data?.items ?? [];
  const words = t.board.audit;

  const settle = (auditId: number, verdict: "passed" | "failed", note?: string): Promise<unknown> =>
    post("/v1/audits/settle", { project_id: projectId, audit_id: auditId, verdict, note: note?.trim() ? note : undefined });

  return (
    <>
      <Bar onRefresh={audits.reload} busy={audits.loading}>
        {data && data.considered > 0 ? <span data-testid="audit-drawn">{words.drawn(data.drawn, data.considered)}</span> : null}
      </Bar>
      <ErrorNote error={audits.error} />
      <ErrorNote error={act.error} />
      {audits.loading && !data ? <Loading /> : null}
      {data && items.length === 0 ? <Empty title={words.emptyTitle} next={words.emptyNext} /> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {items.map((sample) => (
          <li key={sample.id} data-testid="audit" className={sample.verdict ? "is-past" : ""}>
            <p className="record-text">
              {sample.title} <span className="quiet">{words.task(sample.task_id)}</span>
            </p>
            <p className="quiet row wrap">
              <CheckLabel label={sample.label} />
              <span data-testid="audit-verdict">{words.verdict(sample.verdict ?? words.waiting)}</span>
              {!sample.verdict && sample.expires_at ? <span>{words.expires(formatDateTime(sample.expires_at))}</span> : null}
            </p>
            <dl className="pairs">
              <div>
                <dt>{words.evidence}</dt>
                <dd>{sample.evidence ? <AgentText text={sample.evidence} /> : words.noEvidence}</dd>
              </div>
            </dl>
            {sample.verdict ? null : failing === sample.id ? (
              <TextForm
                label={words.noteLabel}
                submit={words.failSubmit}
                multiline
                focus
                onCancel={() => setFailing(null)}
                onSubmit={async (note) => {
                  await settle(sample.id, "failed", note);
                  setFailing(null);
                  audits.reload();
                  onChanged();
                }}
              />
            ) : (
              <div className="row wrap">
                <button
                  type="button"
                  className="button small primary"
                  disabled={act.busy}
                  onClick={() => void act.run(() => settle(sample.id, "passed"))}
                >
                  {words.pass}
                  <span className="visually-hidden"> {words.of(sample.title)}</span>
                </button>
                <button type="button" className="button small" disabled={act.busy} onClick={() => setFailing(sample.id)}>
                  {words.fail}
                  <span className="visually-hidden"> {words.of(sample.title)}</span>
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
