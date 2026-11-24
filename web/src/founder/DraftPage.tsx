/**
 * Drafting a project by talking with the Founder (FND-1, FND-3, FND-4, FND-5, FND-12, FND-13):
 * `/draft` starts a conversation, `/draft/:draftingId` goes on with one, and
 * `/draft/:draftingId/review` is the whole draft on one screen before it is created.
 *
 * The page leads with what is happening now and the one thing to do (P18). Below it, the
 * conversation, and beside it what is left before the project can be created, every decision,
 * and the draft as it stands. It uses the full width: the columns follow the room the page has.
 */
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorNote, Loading } from "../components/common";
import { usePageTitle } from "../needs/NeedsYou";
import { t } from "../strings";
import { settingsWords } from "../strings.settings";
import { Conversation } from "./Conversation";
import { DecisionRail } from "./DecisionRail";
import { DraftComposer, type ComposerMode } from "./DraftComposer";
import { DraftNeeds } from "./DraftNeeds";
import { DraftRail } from "./DraftRail";
import { FounderSetupNote, isNoModelFailure, lastSaid } from "./FounderSetupNote";
import { draftSummary, gradeOf, nowOf, stageOf, stepOf, visibleLines } from "./logic";
import { NowStrip } from "./NowStrip";
import { QuickProgress } from "./QuickProgress";
import { Readiness } from "./Readiness";
import { ReadyChecklist } from "./ReadyChecklist";
import { RoundForm } from "./RoundForm";
import { StartForm } from "./StartForm";
import { Steps } from "./Steps";
import { useDrafting } from "./useDrafting";

export function DraftLoading({ loadError }: { loadError: unknown }): JSX.Element {
  const words = t.founder;
  return (
    <main className="page-main">
      <h1>{words.page.draftTitle}</h1>
      {loadError ? (
        <>
          <ErrorNote error={loadError} />
          <p>
            <Link to="/draft">{words.ready.failedNext}</Link>
          </p>
        </>
      ) : (
        <Loading />
      )}
    </main>
  );
}

function Drafting({ draftingId }: { draftingId: string }): JSX.Element {
  const words = t.founder;
  const navigate = useNavigate();
  const { state, loadError, error, busy, created, actions } = useDrafting(draftingId);
  const { view, reply } = state;
  if (!view) return <DraftLoading loadError={loadError} />;

  const stage = stageOf(view);
  const draft = draftSummary(view.draft);
  const talking = view.state === "drafting" && !view.quick;
  const asking = talking && stage === "you" && view.questions.length > 0;
  const mode: ComposerMode = stage === "founder" ? "working" : asking ? "questions" : "open";
  const start = (): void => {
    void actions.start().then((projectId) => {
      if (projectId) navigate(`/projects/${projectId}?squad=hired`);
    });
  };

  return (
    <div className="draft-shell">
      <header className="draft-top">
        <div className="draft-title">
          <p className="eyebrow">{words.page.draftTitle}</p>
          <h1 data-testid="draft-heading">{draft?.name || words.brief.untitled}</h1>
        </div>
        <Steps current={stepOf(view, false)} />
      </header>
      <NowStrip
        now={nowOf(view)}
        draftingId={draftingId}
        busy={busy}
        working={state.working}
        workingSince={state.workingSince}
        offerRest={talking && stage === "you" && (draft !== null || view.questions.length > 0)}
        onAcceptRest={actions.acceptRest}
      />
      <div className="draft-grid">
        <main className="draft-main" aria-label={words.page.mainLabel}>
          {state.dropped && !state.live ? (
            <p className="offline" role="status">
              {words.talk.offline}
            </p>
          ) : null}
          <Conversation lines={visibleLines(view.lines, talking ? view.questions : [])} reply={reply} />
          {view.failure && view.state === "drafting" && stage !== "founder" ? (
            isNoModelFailure(view.failure) ? (
              <FounderSetupNote
                when="failed"
                returnTo={`/draft/${draftingId}`}
                retrying={busy}
                onRetry={() => void actions.say(lastSaid(view.lines) ?? settingsWords.setupNote.retryBody)}
              />
            ) : (
              <div className="note note-error" role="alert" data-testid="turn-failure">
                <p className="note-title">{words.talk.failureTitle}</p>
                <p className="note-hint">{view.failure}</p>
                <p className="note-hint">{words.talk.failureNext}</p>
              </div>
            )
          ) : null}
          {view.quick ? <QuickProgress state={view.state} /> : null}
          {asking ? <RoundForm questions={view.questions} busy={busy} onSubmit={actions.answerAll} /> : null}
          <ErrorNote error={error} />
          {stage === "done" || stage === "failed" ? (
            <Readiness
              view={view}
              stage={stage}
              created={created}
              busy={busy}
              onCreate={() => void actions.create()}
              onStart={start}
            />
          ) : null}
          {talking ? <DraftComposer mode={mode} busy={busy} onSend={actions.say} /> : null}
          {view.state !== "drafting" && !view.quick ? <p className="quiet">{words.talk.closed}</p> : null}
        </main>
        <aside className="draft-side" aria-label={words.page.sideLabel}>
          <div className="draft-progress">
            <ReadyChecklist view={view} stage={stage} grade={gradeOf(view.grade)} />
            <DecisionRail decisions={view.decisions} ledger={view.ledger} />
          </div>
          <div className="draft-brief">
            <DraftRail draft={draft} rulesHit={view.rules_hit} />
            <DraftNeeds needs={view.needs ?? []} />
          </div>
        </aside>
      </div>
    </div>
  );
}

export function DraftPage(): JSX.Element {
  const words = t.founder.page;
  const { draftingId } = useParams();
  usePageTitle(words.title);

  return draftingId ? (
    <div className="draft-page">
      <Drafting key={draftingId} draftingId={draftingId} />
    </div>
  ) : (
    <main className="content narrow draft-start">
      <h1 id="start-title">{words.title}</h1>
      <StartForm />
    </main>
  );
}
