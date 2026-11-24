/** One task: what it asks for, how it is checked, each attempt, and who checked it in the end. */
import { ChevronLeft, RefreshCw } from "lucide-react";
import { useEffect, useRef } from "react";
import { get } from "../../api/client";
import { ErrorNote, Pre } from "../../components/common";
import { Loading } from "../kit";
import { formatDateTime } from "../../lib/format";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { isClosed, whoChecked } from "./logic";
import { AgentText, CheckLabel, StateTag, type BoardTabProps } from "./parts";
import { useAgentName } from "../../squad/names";

interface Props extends BoardTabProps {
  taskId: number;
  onBack(): void;
  /**
   * "sheet" when shown in a sheet that already carries the task's title and a close button: the
   * back button and the title are left out, and focus stays with the sheet.
   */
  variant?: "page" | "sheet";
}

export function TaskDetail({ projectId, changes, taskId, onBack, variant = "page" }: Props): JSX.Element {
  const detail = useLoad(() => get("/v1/tasks/show", { project_id: projectId, task_id: taskId }), [projectId, taskId, changes]);
  const heading = useRef<HTMLHeadingElement>(null);
  const task = detail.data;
  const words = t.board.detail;
  const nameOf = useAgentName();
  const shown = task !== undefined;

  const inSheet = variant === "sheet";
  useEffect(() => {
    if (shown && !inSheet) heading.current?.focus();
  }, [shown, inSheet]);

  return (
    <div data-testid="task-detail">
      {inSheet ? null : (
        <div className="row wrap board-bar">
          <button type="button" className="button small ghost back-button" onClick={onBack}>
            <ChevronLeft size={16} aria-hidden="true" />
            {words.back}
          </button>
          <span className="spacer" />
          <button type="button" className="button small ghost" onClick={detail.reload} disabled={detail.loading}>
            <RefreshCw size={14} aria-hidden="true" />
            {t.board.refresh}
          </button>
        </div>
      )}
      <ErrorNote error={detail.error} />
      {detail.loading && !task ? <Loading /> : null}
      {task ? (
        <>
          {inSheet ? null : (
            <h3 tabIndex={-1} ref={heading}>
              {words.title(task.id, task.title)}
            </h3>
          )}
          <p className="row wrap">
            <StateTag state={task.state} />
            <CheckLabel label={task.label} />
          </p>
          {isClosed(task.state) ? (
            <p className="note" data-testid="who-checked">
              <strong>{words.whoChecked}:</strong> {whoChecked(task.label)}
            </p>
          ) : null}
          {task.audit ? (
            <p className="note" data-testid="audit-verdict">
              <strong>{words.audit}:</strong> {words.auditVerdict(task.audit)}
            </p>
          ) : null}
          <dl className="pairs">
            {task.reason ? (
              <div data-testid="task-reason">
                <dt>{words.reason}</dt>
                <dd>
                  <AgentText text={task.reason} />
                </dd>
              </div>
            ) : null}
            <div>
              <dt>{words.goal}</dt>
              <dd>
                <AgentText text={task.goal} />
              </dd>
            </div>
            <div>
              <dt>{words.test}</dt>
              <dd>
                <AgentText text={task.success_test} />
                <p className="quiet" data-testid="test-kind">
                  {words.testKinds[task.test_kind] ?? task.test_kind}
                </p>
              </dd>
            </div>
            <div>
              <dt>{words.testFiles}</dt>
              <dd>
                {task.test_files.length === 0 ? (
                  words.noTestFiles
                ) : (
                  <ul className="plain">
                    {task.test_files.map((file) => (
                      <li key={file}>
                        <code>{file}</code>
                      </li>
                    ))}
                  </ul>
                )}
              </dd>
            </div>
            <div>
              <dt>{words.serves}</dt>
              <dd>{task.serves ? <AgentText text={task.serves} /> : words.servesNothing}</dd>
            </div>
            <div>
              <dt>{words.author}</dt>
              <dd>{nameOf(task.author).name}</dd>
            </div>
            <div>
              <dt>{words.holder}</dt>
              <dd>{task.claimant ? nameOf(task.claimant).name : words.nobody}</dd>
            </div>
            {task.team ? (
              <div>
                <dt>{words.team}</dt>
                <dd>{task.team}</dd>
              </div>
            ) : null}
            <div>
              <dt>{words.evidence}</dt>
              <dd data-testid="task-evidence">
                {task.completion_evidence ? <AgentText text={task.completion_evidence} /> : words.noEvidence}
              </dd>
            </div>
            {task.failures > 0 ? (
              <div>
                <dt>{words.failures}</dt>
                <dd>{t.board.tasks.failures(task.failures)}</dd>
              </div>
            ) : null}
            <div>
              <dt>{words.created}</dt>
              <dd>{formatDateTime(task.created_at)}</dd>
            </div>
            {task.closed_at ? (
              <div>
                <dt>{words.closed}</dt>
                <dd>{formatDateTime(task.closed_at)}</dd>
              </div>
            ) : null}
          </dl>
          <h3>{words.attempts}</h3>
          {task.attempts.length === 0 ? <p className="quiet">{words.noAttempts}</p> : null}
          <ol className="records plain">
            {task.attempts.map((attempt, index) => (
              <li key={`${attempt.at}-${index}`} data-testid="attempt">
                <p className="record-text">{words.attempt(index + 1, nameOf(attempt.by).name, formatDateTime(attempt.at))}</p>
                <p>
                  <AgentText text={attempt.evidence} />
                </p>
                <p data-testid="attempt-result">{words.result(attempt.result)}</p>
                {attempt.output ? (
                  <>
                    <p className="quiet">{words.output}</p>
                    <Pre className="check-output">{attempt.output}</Pre>
                  </>
                ) : (
                  <p className="quiet">{words.noOutput}</p>
                )}
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </div>
  );
}
