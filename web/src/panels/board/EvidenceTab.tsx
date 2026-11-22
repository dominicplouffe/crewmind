/** Outside evidence: pages and quotes agents filed, and whether the platform found the quote there. */
import { FileSearch } from "lucide-react";
import { get } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { Empty, Loading } from "../kit";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { webAddress } from "./logic";
import { AgentText, Bar, type BoardTabProps } from "./parts";

export function EvidenceTab({ projectId, changes }: BoardTabProps): JSX.Element {
  const evidence = useLoad(() => get("/v1/evidence/list", { project_id: projectId }), [projectId, changes]);
  const items = evidence.data?.items ?? [];
  const words = t.board.evidence;

  return (
    <>
      <Bar onRefresh={evidence.reload} busy={evidence.loading} />
      <ErrorNote error={evidence.error} />
      {evidence.loading && !evidence.data ? <Loading /> : null}
      {evidence.data && items.length === 0 ? <Empty icon={FileSearch} title={words.emptyTitle} next={words.emptyNext} /> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {items.map((item) => {
          const href = webAddress(item.url);
          return (
            <li key={item.id} data-testid="evidence">
              <p className="record-text">
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {item.url} <span className="visually-hidden">{words.newTab}</span>
                  </a>
                ) : (
                  <AgentText text={item.url} />
                )}
              </p>
              <blockquote className="quote">
                <AgentText text={item.quote} />
              </blockquote>
              <p className="quiet row wrap">
                <span className={`marker evidence-${item.state}`} data-testid="evidence-state">
                  {item.state === "pending" ? words.pending : item.state}
                </span>
                <span>
                  {words.filedBy(item.filed_by)}
                  {item.task_id == null ? "" : ` ${words.task(item.task_id)}`}
                </span>
              </p>
              {item.failure ? <p data-testid="evidence-failure">{words.failure(item.failure)}</p> : null}
            </li>
          );
        })}
      </ul>
    </>
  );
}
