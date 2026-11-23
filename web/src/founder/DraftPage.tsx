/**
 * Drafting a project by talking with the Founder (FND-1, FND-3, FND-5, FND-12, FND-13): `/draft`
 * starts a conversation, `/draft/:draftingId` goes on with one. The conversation and what waits on
 * the person are in the main column; the ledger, the goal grade and the draft are beside it.
 */
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorNote, Loading } from "../components/common";
import { usePageTitle } from "../needs/NeedsYou";
import { t } from "../strings";
import { settingsWords } from "../strings.settings";
import { AcceptRest } from "./AcceptRest";
import { Conversation } from "./Conversation";
import { DraftComposer } from "./DraftComposer";
import { DraftSummary } from "./DraftSummary";
import { FounderSetupNote, isNoModelFailure, lastSaid } from "./FounderSetupNote";
import { GoalGrade } from "./GoalGrade";
import { Ledger } from "./Ledger";
import { draftSummary, gradeOf, stageOf, visibleLines } from "./logic";
import { QuestionCard } from "./QuestionCard";
import { QuickProgress } from "./QuickProgress";
import { Readiness } from "./Readiness";
import { StartForm } from "./StartForm";
import { useDrafting } from "./useDrafting";
import { WorkingLine } from "./WorkingLine";

function Drafting({ draftingId }: { draftingId: string }): JSX.Element {
  const words = t.founder;
  const navigate = useNavigate();
  const { state, loadError, error, busy, created, actions } = useDrafting(draftingId);
  const { view, reply } = state;

  if (!view) {
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

  const stage = stageOf(view);
  const draft = draftSummary(view.draft);
  const talking = view.state === "drafting" && !view.quick;
  const start = (): void => {
    void actions.start().then((projectId) => {
      if (projectId) navigate(`/projects/${projectId}?crew=hired`);
    });
  };

  return (
    <div className="draft-columns">
      <main className="draft-main" aria-label={words.page.mainLabel}>
        <h1 data-testid="draft-heading">{draft?.name || words.page.draftTitle}</h1>
        {state.dropped && !state.live ? (
          <p className="offline" role="status">
            {words.talk.offline}
          </p>
        ) : null}
        <Conversation lines={visibleLines(view.lines, talking ? view.questions : [])} reply={reply} />
        {stage === "founder" && !reply ? (
          <WorkingLine doing={state.working} since={state.workingSince} />
        ) : null}
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
        {talking
          ? view.questions.map((question) => (
              <QuestionCard key={question.id} question={question} busy={busy} onAnswer={actions.answer} />
            ))
          : null}
        <ErrorNote error={error} />
        {talking && stage === "you" && (draft || view.questions.length > 0) ? <AcceptRest busy={busy} onAccept={actions.acceptRest} /> : null}
        <Readiness view={view} stage={stage} created={created} busy={busy} onCreate={() => void actions.create()} onStart={start} />
        {talking ? <DraftComposer busy={busy} onSend={actions.say} /> : null}
        {view.state !== "drafting" && !view.quick ? <p className="quiet">{words.talk.closed}</p> : null}
      </main>
      {/* The side column scrolls on its own, so it takes focus for keyboard users (WCAG 2.1.1). */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <aside className="draft-side" aria-label={words.page.sideLabel} tabIndex={0}>
        <Ledger ledger={view.ledger} />
        <GoalGrade grade={gradeOf(view.grade)} />
        <DraftSummary draft={draft} rehearsal={view.rehearsal} rulesHit={view.rules_hit} />
      </aside>
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
