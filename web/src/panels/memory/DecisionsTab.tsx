/** Closed decisions: decide, reopen, rule again; and answer agents' requests to reopen one. */
import { Scale } from "lucide-react";
import { useState } from "react";
import { get, post, type Decision, type ReopenRequest } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { Empty, Loading } from "../kit";
import { formatDateTime } from "../../lib/format";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { ServerNote, Tag, TextForm, stateName, useAct, type TabProps } from "./parts";

interface Props extends TabProps {
  onJump(messageId: number): void;
  onFile(name: string): void;
}

export function DecisionsTab({ projectId, changes, onChanged, onJump, onFile }: Props): JSX.Element {
  const decisions = useLoad(() => get("/v1/decisions/list", { project_id: projectId }), [projectId, changes]);
  const requests = useLoad(() => get("/v1/decisions/requests", { project_id: projectId }), [projectId, changes]);
  const [note, setNote] = useState<string | null>(null);
  const reload = (): void => {
    decisions.reload();
    requests.reload();
    onChanged();
  };
  const act = useAct(reload);
  const items = decisions.data?.items ?? [];
  const asked = requests.data?.items ?? [];
  const words = t.memory.decisions;

  const change = (work: () => Promise<Decision>): Promise<boolean> =>
    act.run(async () => {
      setNote((await work()).note ?? null);
    });
  const topicOf = (request: ReopenRequest): string => items.find((item) => item.id === request.decision_id)?.topic ?? "";

  return (
    <>
      {asked.length > 0 ? (
        <section aria-label={words.requests}>
          <h3>{words.requests}</h3>
          <ul className="records plain">
            {asked.map((request) => (
              <li key={request.id} data-testid="reopen-request">
                <p className="record-text">{words.request(request.by, request.decision_id, topicOf(request))}</p>
                <p>{request.reason}</p>
                <p className="quiet">
                  {words.evidence}:{" "}
                  {request.evidence.map((item) => {
                    const kind = stateName(words.evidenceKinds, item.kind);
                    return (
                      <button
                        key={`${item.kind}-${item.ref}`}
                        type="button"
                        className="link evidence"
                        onClick={() => (item.kind === "message" ? onJump(Number(item.ref)) : onFile(item.ref))}
                      >
                        {words.openEvidence(kind, item.ref)}
                      </button>
                    );
                  })}
                </p>
                {request.approved === null ? (
                  <div className="row wrap">
                    {([true, false] as const).map((approve) => (
                      <button
                        key={String(approve)}
                        type="button"
                        className={approve ? "button small primary" : "button small"}
                        disabled={act.busy}
                        onClick={() =>
                          void change(() =>
                            post("/v1/decisions/answer", { project_id: projectId, request_id: request.id, approve }),
                          )
                        }
                      >
                        {approve ? t.listening.approve : t.listening.decline}
                        <span className="visually-hidden"> {t.listening.requestOf(request.id)}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="quiet">{t.listening.requestAnswered(request.approved)}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <TextForm
        label={words.addLabel}
        submit={words.add}
        onSubmit={async (text) => {
          const decision = await post("/v1/decisions/decide", { project_id: projectId, text });
          setNote(decision.note ?? null);
          reload();
        }}
      />
      <ServerNote text={note} />
      <ErrorNote error={decisions.error} />
      <ErrorNote error={requests.error} />
      <ErrorNote error={act.error} />
      {decisions.loading && !decisions.data ? <Loading /> : null}
      {decisions.data && items.length === 0 ? <Empty icon={Scale} title={words.emptyTitle} next={words.emptyNext} /> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {items.map((decision) => (
          <li key={decision.id} data-testid="decision">
            <p className="record-text">
              <strong>{decision.topic}:</strong> {decision.ruling}
            </p>
            <p className="quiet">
              <Tag>{stateName(words.states, decision.state)}</Tag> {words.decided(formatDateTime(decision.decided_at))}
            </p>
            {decision.state === "closed" ? (
              <button
                type="button"
                className="button small"
                disabled={act.busy}
                onClick={() =>
                  void change(() => post("/v1/decisions/reopen", { project_id: projectId, decision_id: decision.id }))
                }
              >
                {words.reopen}
                <span className="visually-hidden"> {decision.topic}</span>
              </button>
            ) : null}
            {decision.state === "reopened" ? (
              <TextForm
                label={words.ruleLabel(decision.topic)}
                submit={words.rule}
                onSubmit={async (ruling) => {
                  const result = await post("/v1/decisions/rule", {
                    project_id: projectId,
                    decision_id: decision.id,
                    ruling,
                  });
                  setNote(result.note ?? null);
                  reload();
                }}
              />
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}
