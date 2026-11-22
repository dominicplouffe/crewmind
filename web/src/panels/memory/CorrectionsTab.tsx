/** Corrections: each time the chairman said "not what I asked", with the question and the agent. */
import { PenLine } from "lucide-react";
import { get, post } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { Empty, Loading } from "../kit";
import { formatDateTime } from "../../lib/format";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { Tag, stateName, useAct, type TabProps } from "./parts";

export function CorrectionsTab({ projectId, changes, onChanged }: TabProps): JSX.Element {
  const corrections = useLoad(() => get("/v1/corrections/list", { project_id: projectId }), [projectId, changes]);
  const act = useAct(() => {
    corrections.reload();
    onChanged();
  });
  const items = corrections.data?.items ?? [];
  const words = t.memory.corrections;

  return (
    <>
      <ErrorNote error={corrections.error} />
      <ErrorNote error={act.error} />
      {corrections.loading && !corrections.data ? <Loading /> : null}
      {corrections.data && items.length === 0 ? <Empty icon={PenLine} title={words.emptyTitle} next={words.emptyNext} /> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {items.map((correction) => (
          <li key={correction.id} data-testid="correction" className={correction.state === "active" ? "" : "is-past"}>
            <dl className="pairs">
              <div>
                <dt>{words.question}</dt>
                <dd>{correction.question}</dd>
              </div>
              <div>
                <dt>{words.words}</dt>
                <dd>{correction.words}</dd>
              </div>
            </dl>
            <p className="quiet">
              <Tag>{stateName(words.states, correction.state)}</Tag> {words.agent(correction.agent)}
              {correction.expires_at ? ` · ${words.expires(formatDateTime(correction.expires_at))}` : ""}
            </p>
            {correction.note ? <p className="note">{correction.note}</p> : null}
            {correction.state === "active" ? (
              <button
                type="button"
                className="button small"
                disabled={act.busy}
                onClick={() =>
                  void act.run(() =>
                    post("/v1/corrections/remove", { project_id: projectId, correction_id: correction.id }),
                  )
                }
              >
                {words.remove}
                <span className="visually-hidden"> {correction.words}</span>
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}
