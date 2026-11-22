/**
 * One agent up close: its role and team, the model it runs on, its listening score (CHAT-12),
 * its recent runs as sentences (each opens the run), and the files it last changed.
 */
import { ChevronRight, MessageSquare } from "lucide-react";
import { get } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatNumber } from "../lib/format";
import { fromNow, tokens } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { crew, runWords } from "../strings.crew";
import { Avatar } from "../ui/Avatar";
import { Sheet } from "../ui/Sheet";
import { Skeleton } from "../ui/Skeleton";
import { Pill } from "../ui/Status";
import { recentRuns, runSentence, type CrewMember, type Run } from "./logic";
import { STATUS_TONE } from "./tone";

const RECENT_RUNS = 12;
const RECENT_FILES = 8;

interface Props {
  projectId: string;
  changes: number;
  member: CrewMember;
  runs: Run[];
  onClose(): void;
  onMessage(name: string): void;
  onOpenRun(runId: string): void;
}

export function AgentSheet({ projectId, changes, member, runs, onClose, onMessage, onOpenRun }: Props): JSX.Element {
  const models = useLoad(() => get("/v1/models/show", { project_id: projectId }), [projectId, changes]);
  const artifacts = useLoad(() => get("/v1/artifacts/list", { project_id: projectId }), [projectId, changes]);
  const model = models.data?.seats.find((seat) => seat.seat === member.name);
  const files = (artifacts.data?.items ?? [])
    .filter((item) => item.last_author === member.name)
    .sort((a, b) => Date.parse(b.last_change) - Date.parse(a.last_change))
    .slice(0, RECENT_FILES);
  const recent = recentRuns(runs, member.name, RECENT_RUNS);

  return (
    <Sheet
      title={member.name}
      subtitle={crew.sheet.subtitle(member.role, member.team)}
      onClose={onClose}
      size="lg"
      testId="agent-sheet"
      actions={
        <button type="button" className="button primary small" onClick={() => onMessage(member.name)}>
          <MessageSquare size={16} aria-hidden="true" />
          {crew.sheet.message(member.name)}
        </button>
      }
    >
      <div className="agent-hero">
        <Avatar name={member.name} size="xl" status={member.status} />
        <div className="agent-hero-text">
          <Pill tone={STATUS_TONE[member.status]} live={member.status === "working"}>
            {crew.status[member.status]}
          </Pill>
          <p className="agent-now">{member.now}</p>
          <p className="quiet tabular">{crew.sheet.usedLine(tokens(member.tokens), member.runs)}</p>
        </div>
      </div>

      <section aria-labelledby="agent-about" className="agent-section">
        <h3 id="agent-about" className="eyebrow">
          {crew.sheet.about}
        </h3>
        <dl className="pairs">
          <div>
            <dt>{crew.sheet.role}</dt>
            <dd>{member.role}</dd>
          </div>
          <div>
            <dt>{crew.sheet.team}</dt>
            <dd>{member.team ?? crew.sheet.noTeam}</dd>
          </div>
          <div>
            <dt>{crew.sheet.kind}</dt>
            <dd>{crew.sheet.kinds[member.kind] ?? member.kind}</dd>
          </div>
          <div>
            <dt>{crew.sheet.model}</dt>
            <dd>
              {models.data === undefined && !models.error ? (
                <span className="skeleton line" aria-hidden="true" />
              ) : model?.model ? (
                crew.sheet.modelLine(model.model, model.provider ?? "")
              ) : (
                crew.sheet.noModel
              )}
              {model?.note ? <p className="note">{model.note}</p> : null}
            </dd>
          </div>
          {model ? (
            <div>
              <dt>{crew.sheet.quality}</dt>
              <dd>{crew.sheet.qualityLine(model.asked_class, model.effort)}</dd>
            </div>
          ) : null}
          {model?.paid_by ? (
            <div>
              <dt>{crew.sheet.paidBy}</dt>
              <dd>{model.paid_by}</dd>
            </div>
          ) : null}
          <div>
            <dt>{crew.sheet.listening}</dt>
            <dd data-testid="listening-score">
              {member.listeningScore === null
                ? crew.sheet.noReplies
                : crew.sheet.listeningLine(formatNumber(member.listeningScore), member.corrections, member.replies)}
              <span className="quiet agent-hint">{crew.sheet.listeningHint}</span>
            </dd>
          </div>
        </dl>
        <ErrorNote error={models.error} />
      </section>

      <section aria-labelledby="agent-runs" className="agent-section">
        <h3 id="agent-runs" className="eyebrow">
          {crew.sheet.recent}
        </h3>
        {recent.length === 0 ? <p className="quiet">{crew.sheet.noRuns}</p> : null}
        <ol className="plain agent-runs">
          {recent.map((run) => {
            const sentence = runSentence(run);
            return (
              <li key={run.run_id} className={`agent-run tone-${sentence.tone}`}>
                <span className="agent-run-dot" aria-hidden="true" />
                <div className="agent-run-body">
                  <button type="button" className="agent-run-open" onClick={() => onOpenRun(run.run_id)}>
                    <span>
                      <span className="agent-run-action">{sentence.action}</span>
                      <span className="quiet tabular">
                        {sentence.when}
                        {sentence.tokens ? ` · ${sentence.tokens}` : ""}
                      </span>
                    </span>
                    <ChevronRight size={16} aria-hidden="true" />
                    <span className="visually-hidden">{crew.sheet.openRun}</span>
                  </button>
                  <details className="agent-tech">
                    <summary>{runWords.technical}</summary>
                    <dl className="pairs">
                      {(
                        [
                          ["run", sentence.technical.run],
                          ["kind", sentence.technical.kind],
                          ["state", sentence.technical.state],
                          ["reasons", sentence.technical.reasons],
                          ["detail", sentence.technical.detail],
                          ["model", sentence.technical.model],
                          ["tokens", formatNumber(sentence.technical.tokens)],
                        ] as const
                      )
                        .filter(([, value]) => value)
                        .map(([key, value]) => (
                          <div key={key}>
                            <dt>{runWords.technicalFields[key]}</dt>
                            <dd>
                              <code>{value}</code>
                            </dd>
                          </div>
                        ))}
                    </dl>
                  </details>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="agent-files" className="agent-section">
        <h3 id="agent-files" className="eyebrow">
          {crew.sheet.files}
        </h3>
        <ErrorNote error={artifacts.error} />
        {artifacts.data === undefined && !artifacts.error ? <Skeleton lines={2} label={crew.sheet.loadingDetails} /> : null}
        {artifacts.data && files.length === 0 ? <p className="quiet">{crew.sheet.noFiles}</p> : null}
        <ul className="plain agent-files">
          {files.map((file) => (
            <li key={file.name}>
              <span className="agent-file-name">{file.name}</span>
              <span className="quiet">{fromNow(file.last_change)}</span>
            </li>
          ))}
        </ul>
      </section>
    </Sheet>
  );
}
