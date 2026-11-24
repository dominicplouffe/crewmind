/**
 * The whole draft on one screen, before it becomes a project (FND-5, FND-13): what it is, the
 * goal in full, the squad, every decision with where it came from, how the goal grades and what
 * the rehearsal found. Creating the project here confirms the ledger.
 */
import { ArrowLeft } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorNote, Markdown } from "../components/common";
import { usePageTitle } from "../needs/NeedsYou";
import { t } from "../strings";
import { DraftLoading } from "./DraftPage";
import { SquadList, ProjectFacts, SettingsList } from "./DraftRail";
import { GoalGrade } from "./GoalGrade";
import { decisionName, draftSummary, gradeOf, sourceTag, stageOf, stepOf } from "./logic";
import { Readiness } from "./Readiness";
import { Steps } from "./Steps";
import { useDrafting } from "./useDrafting";

function Review({ draftingId }: { draftingId: string }): JSX.Element {
  const words = t.founder;
  const review = words.review;
  const navigate = useNavigate();
  const { state, loadError, error, busy, created, actions } = useDrafting(draftingId);
  const { view } = state;
  if (!view) return <DraftLoading loadError={loadError} />;

  const stage = stageOf(view);
  const draft = draftSummary(view.draft);
  const grade = gradeOf(view.grade);
  const back = (
    <Link to={`/draft/${draftingId}`} className="back-link">
      <ArrowLeft size={16} aria-hidden="true" />
      {review.back}
    </Link>
  );
  const start = (): void => {
    void actions.start().then((projectId) => {
      if (projectId) navigate(`/projects/${projectId}?squad=hired`);
    });
  };

  return (
    <div className="draft-shell review-shell">
      <header className="draft-top">
        <div className="draft-title">
          {back}
          <h1 data-testid="review-heading">{review.title(draft?.name ?? "")}</h1>
          <p className="quiet">{review.lead}</p>
        </div>
        <Steps current={stepOf(view, true)} />
      </header>
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
      {stage !== "ready" && stage !== "done" && stage !== "failed" ? (
        <section className="note" data-testid="review-not-ready">
          <h2>{review.notReadyTitle}</h2>
          <ul>
            {view.not_ready_because.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          {back}
        </section>
      ) : null}
      {draft && stage !== "failed" ? (
        <div className="review-grid" data-testid="review">
          <section className="rail-card review-wide" aria-labelledby="review-goal">
            <header className="rail-head">
              <h2 id="review-goal">{words.side.goal}</h2>
              {grade ? (
                <span className={grade.ready ? "badge grade-present" : "badge grade-missing"}>
                  {grade.ready ? words.side.gradeReady : words.side.gradeNotReady}
                </span>
              ) : null}
            </header>
            <Markdown source={draft.goal} className="draft-goal" />
            {grade ? (
              <details className="fold">
                <summary>{words.draftRail.gradeShow}</summary>
                <p data-testid="grade-summary">{grade.summary}</p>
                <GoalGrade grade={grade} />
              </details>
            ) : null}
          </section>
          <div className="rail-stack">
            <section className="rail-card" aria-labelledby="review-project" data-testid="draft">
              <header className="rail-head">
                <h2 id="review-project">{words.draftRail.project}</h2>
              </header>
              <ProjectFacts draft={draft} />
              {draft.settings.length > 0 ? (
                <>
                  <h3 className="rail-subtitle">{words.side.settings}</h3>
                  <SettingsList draft={draft} />
                </>
              ) : null}
            </section>
            <section className="rail-card" aria-labelledby="review-squad">
              <header className="rail-head">
                <h2 id="review-squad">{words.draftRail.squad}</h2>
              </header>
              <SquadList draft={draft} />
            </section>
            <section className="rail-card" aria-labelledby="review-rehearsal">
              <header className="rail-head">
                <h2 id="review-rehearsal">{words.side.rehearsal}</h2>
              </header>
              <p className={view.rehearsal ? undefined : "quiet"} data-testid="draft-rehearsal">
                {view.rehearsal ?? words.side.rehearsalNone}
              </p>
            </section>
          </div>
          <section className="rail-card review-wide" aria-labelledby="review-decisions">
            <header className="rail-head">
              <h2 id="review-decisions">{review.decisions}</h2>
            </header>
            <table className="review-table">
              <thead>
                <tr>
                  <th scope="col">{review.decisionCols.what}</th>
                  <th scope="col">{review.decisionCols.value}</th>
                  <th scope="col">{review.decisionCols.source}</th>
                </tr>
              </thead>
              <tbody>
                {view.ledger.map((line) => (
                  <tr key={line.settles} data-testid="ledger-line" data-settles={line.settles} data-source={line.source}>
                    <th scope="row">{decisionName(line.settles)}</th>
                    <td>{line.value}</td>
                    <td>
                      <span className={`badge source-${line.source}`}>{sourceTag(line.source)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      ) : null}
      {stage === "ready" ? (
        <footer className="review-foot" data-testid="readiness">
          <p className="quiet">{review.createNote}</p>
          <div className="row wrap">
            {back}
            <button type="button" className="button primary large" disabled={busy} onClick={() => void actions.create()}>
              {busy ? words.ready.creating : words.ready.create}
            </button>
          </div>
        </footer>
      ) : null}
    </div>
  );
}

export function DraftReviewPage(): JSX.Element {
  const { draftingId } = useParams();
  usePageTitle(t.founder.page.title);
  return draftingId ? (
    <div className="draft-page">
      <Review key={draftingId} draftingId={draftingId} />
    </div>
  ) : (
    <DraftLoading loadError={null} />
  );
}
