/**
 * The first thing on the drafting page (FND-1, FND-5, P17, P18): one sentence on what is happening
 * now, one on what that means for the person, and the one action that moves the draft on. While the
 * Founder works it says so, with what it is doing and for how long, so the page is never still.
 */
import { ArrowRight, CheckCircle2, CircleAlert, MessageSquareText, PenLine, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { founder as words } from "../strings.founder";
import { AcceptRest } from "./AcceptRest";
import type { Now } from "./logic";
import { WorkingLine } from "./WorkingLine";

interface Props {
  now: Now;
  draftingId: string;
  busy: boolean;
  /** What the Founder reports it is doing, and since when, while it works. */
  working: string;
  workingSince: string;
  /** Offer "use your recommendations for the rest" (FND-15): only while it is the person's turn. */
  offerRest: boolean;
  onAcceptRest(): Promise<boolean>;
}

/** Brings the first question into view and puts focus on its chosen answer: the recommended one, at first. */
function goToQuestions(): void {
  const round = document.querySelector<HTMLElement>('[data-testid="round"]');
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  round?.scrollIntoView({ block: "start", behavior: calm ? "auto" : "smooth" });
  const answer =
    round?.querySelector<HTMLElement>('input[type="radio"]:checked') ?? round?.querySelector<HTMLElement>('input[type="radio"]');
  answer?.focus({ preventScroll: true });
}

function goToComposer(): void {
  const box = document.getElementById("draft-message");
  box?.scrollIntoView({ block: "center" });
  box?.focus({ preventScroll: true });
}

function text(now: Now): { title: string; body: string } {
  const said = words.now;
  switch (now.kind) {
    case "writing-first":
      return said.writingFirst;
    case "updating":
      return said.updating;
    case "questions":
      return { title: said.questions.title(now.count), body: said.questions.body };
    case "your-turn":
      return said.yourTurn;
    case "failed-turn":
      return said.failedTurn;
    case "ready":
      return said.ready;
    case "quick":
      return said.quick;
    case "created":
      return said.created;
    case "ended":
      return said.ended;
  }
}

const TONE: Record<Now["kind"], string> = {
  "writing-first": "working",
  updating: "working",
  quick: "working",
  questions: "ask",
  "your-turn": "ask",
  "failed-turn": "problem",
  ready: "ready",
  created: "ready",
  ended: "problem",
};

function Icon({ now }: { now: Now }): JSX.Element {
  const tone = TONE[now.kind];
  if (tone === "working") return <span className="now-pulse" aria-hidden="true" />;
  if (tone === "problem") return <CircleAlert size={22} aria-hidden="true" />;
  if (tone === "ready") return <CheckCircle2 size={22} aria-hidden="true" />;
  return now.kind === "questions" ? <MessageSquareText size={22} aria-hidden="true" /> : <PenLine size={22} aria-hidden="true" />;
}

export function NowStrip({ now, draftingId, busy, working, workingSince, offerRest, onAcceptRest }: Props): JSX.Element {
  const shown = text(now);
  const tone = TONE[now.kind];
  return (
    <section
      className={`now-strip now-${tone}`}
      aria-label={words.now.label}
      data-testid="now"
      data-now={now.kind}
    >
      <div className="now-icon">
        <Icon now={now} />
      </div>
      <div className="now-text">
        <p className="now-eyebrow">{words.now.eyebrow}</p>
        <h2 className="now-title">{shown.title}</h2>
        <p className="now-body">{shown.body}</p>
        {tone === "working" && now.kind !== "quick" ? <WorkingLine doing={working} since={workingSince} /> : null}
      </div>
      <div className="now-actions">
        {now.kind === "questions" ? (
          <button type="button" className="button primary large" onClick={goToQuestions}>
            {words.now.questions.action(now.count)}
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        ) : null}
        {now.kind === "your-turn" || now.kind === "failed-turn" ? (
          <button type="button" className="button primary large" onClick={goToComposer}>
            {now.kind === "your-turn" ? words.now.yourTurn.action : words.now.failedTurn.action}
          </button>
        ) : null}
        {now.kind === "ready" ? (
          <Link to={`/draft/${draftingId}/review`} className="button primary large" data-testid="go-review">
            <Sparkles size={16} aria-hidden="true" />
            {words.review.go}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        ) : null}
        {offerRest ? <AcceptRest busy={busy} onAccept={onAcceptRest} /> : null}
      </div>
    </section>
  );
}
