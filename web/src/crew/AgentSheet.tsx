/**
 * One agent up close: its role and team, the model it runs on, its listening score (CHAT-12),
 * its recent runs as sentences (each opens the run), and the files it last changed.
 */
import { ChevronRight, MessageSquare, Pencil } from "lucide-react";
import { useState, type FormEvent } from "react";
import { get, post } from "../api/client";
import { ErrorNote, Field } from "../components/common";
import { formatNumber } from "../lib/format";
import { fromNow, tokens } from "../lib/humanize";
import { useLoad } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { crew, runWords } from "../strings.crew";
import { Sheet } from "../ui/Sheet";
import { Skeleton } from "../ui/Skeleton";
import { Pill } from "../ui/Status";
import { recentRuns, runSentence, type CrewMember, type Run } from "./logic";
import { mentionOf } from "./names";
import { StatusFace } from "./parts";
import { STATUS_TONE } from "./tone";

const RECENT_RUNS = 12;
const RECENT_FILES = 8;

interface Props {
  projectId: string;
  changes: number;
  member: CrewMember;
  runs: Run[];
  /** The person chairs the project, so may rename the agent (EXE-18). The server decides either way. */
  canRename?: boolean;
  onClose(): void;
  /** Start a message to the agent: `mention` is what to type after the @. */
  onMessage(mention: string): void;
  onOpenRun(runId: string): void;
  onRenamed?(): void;
}

/** The chairman gives the agent another name; the server tidies it and refuses a taken or empty one. */
function RenameForm({ projectId, member, onDone }: { projectId: string; member: CrewMember; onDone(): void }): JSX.Element {
  const [value, setValue] = useState(member.displayName);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await post("/v1/roster/rename_seat", { project_id: projectId, seat: member.name, display_name: value });
      onDone();
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  };
  return (
    <form className="agent-rename stack" onSubmit={(event) => void submit(event)} data-testid="agent-rename">
      <Field label={crew.sheet.renameLabel(member.displayName)} htmlFor="agent-rename-input">
        <input
          id="agent-rename-input"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          maxLength={100}
          autoFocus
        />
      </Field>
      <ErrorNote error={error} />
      <div className="row">
        <button type="submit" className="button primary small" disabled={saving}>
          {crew.sheet.save}
        </button>
        <button type="button" className="button ghost small" onClick={onDone}>
          {crew.sheet.cancel}
        </button>
      </div>
    </form>
  );
}

export function AgentSheet({
  projectId,
  changes,
  member,
  runs,
  canRename = false,
  onClose,
  onMessage,
  onOpenRun,
  onRenamed,
}: Props): JSX.Element {
  const [renaming, setRenaming] = useState(false);
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
      title={member.displayName}
      subtitle={crew.sheet.subtitle(member.roleLabel, member.team)}
      onClose={onClose}
      size="lg"
      testId="agent-sheet"
      actions={
        <>
          {canRename && !renaming ? (
            <button type="button" className="button small" onClick={() => setRenaming(true)} data-testid="agent-rename-open">
              <Pencil size={16} aria-hidden="true" />
              {crew.sheet.rename}
            </button>
          ) : null}
          <button type="button" className="button primary small" onClick={() => onMessage(mentionOf(member.displayName))}>
            <MessageSquare size={16} aria-hidden="true" />
            {crew.sheet.message(member.displayName)}
          </button>
        </>
      }
    >
      {renaming ? (
        <RenameForm
          projectId={projectId}
          member={member}
          onDone={() => {
            setRenaming(false);
            onRenamed?.();
          }}
        />
      ) : null}
      <div className="agent-hero">
        <StatusFace seat={member.name} size="xl" status={member.status} />
        <div className="agent-hero-text">
          <Pill tone={STATUS_TONE[member.status]} live={member.status === "working"}>
            {member.label}
          </Pill>
          <p className="agent-now">
            {member.now}
            {member.doing ? <span className="quiet"> · {member.doing}</span> : null}
          </p>
          {member.reason ? (
            <p className="crew-card-reason">
              <span className="visually-hidden">{crew.reason}: </span>
              <AgentText text={member.reason} />
            </p>
          ) : null}
          <p className="quiet tabular">{crew.sheet.usedLine(tokens(member.tokens), member.runs)}</p>
        </div>
      </div>

      <section aria-labelledby="agent-about" className="agent-section">
        <h3 id="agent-about" className="eyebrow">
          {crew.sheet.about}
        </h3>
        <dl className="pairs">
          <div>
            <dt>{crew.sheet.name}</dt>
            <dd>
              {member.displayName}
              {member.displayName !== member.name ? <span className="quiet agent-hint">{crew.sheet.seatName(member.name)}</span> : null}
            </dd>
          </div>
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
