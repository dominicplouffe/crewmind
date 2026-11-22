/**
 * One open question of the Founder (FND-3): the question, its options as buttons with the
 * recommended one marked, what the answer changes, and a box for the person's own words.
 * When the card appears, focus goes to the recommended option, so Enter accepts it. A question
 * with no recommendation (who pays) marks nothing and focuses the question itself.
 */
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { t } from "../strings";
import { answerFor, letterOf, type Choice, type Question } from "./logic";

interface Props {
  question: Question;
  busy: boolean;
  /** Sends the answer. Resolves true when the server took it. */
  onAnswer(questionId: number, answer: string): Promise<boolean>;
}

/** Focus is not taken from someone who is in the middle of typing something. */
function typingElsewhere(card: HTMLElement | null): boolean {
  const active = document.activeElement;
  if (!(active instanceof HTMLTextAreaElement || active instanceof HTMLInputElement)) return false;
  return !card?.contains(active) && active.value.trim() !== "";
}

export function QuestionCard({ question, busy, onAnswer }: Props): JSX.Element {
  const words = t.founder.question;
  const id = useId();
  const card = useRef<HTMLElement>(null);
  const heading = useRef<HTMLParagraphElement>(null);
  const recommendedButton = useRef<HTMLButtonElement>(null);
  const [own, setOwn] = useState("");
  const recommended = question.recommended;

  useEffect(() => {
    if (typingElsewhere(card.current)) return;
    (recommendedButton.current ?? heading.current)?.focus();
  }, [question.id]);

  const send = (choice: Choice): void => {
    const answer = answerFor(question, choice);
    if (answer === null || busy) return;
    void onAnswer(question.id, answer).then((taken) => {
      if (taken) setOwn("");
    });
  };

  const submitOwn = (event: FormEvent): void => {
    event.preventDefault();
    send({ kind: "own", text: own });
  };

  // Enter on the question itself accepts the recommendation; on a button or in the box it does what that control does.
  const onKeyDown = (event: KeyboardEvent<HTMLElement>): void => {
    if (event.key !== "Enter" || event.target !== heading.current) return;
    event.preventDefault();
    send({ kind: "recommended" });
  };

  const ownAnswer = answerFor(question, { kind: "own", text: own });
  return (
    // Enter on the focused question accepts the recommendation; every control inside is also operable by itself.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <section
      ref={card}
      className="question-card"
      aria-labelledby={`${id}-title`}
      data-testid="question-card"
      data-settles={question.settles}
      onKeyDown={onKeyDown}
    >
      <h2 id={`${id}-title`} className="question-title">
        {words.title}
      </h2>
      <p className="question-text" id={`${id}-text`} tabIndex={-1} ref={heading}>
        {question.text}
      </p>
      <p className="quiet" id={`${id}-changes`} data-testid="question-changes">
        {words.changes(question.changes)}
      </p>
      <div className="question-options" role="group" aria-label={words.options} aria-describedby={`${id}-text ${id}-changes`}>
        {question.options.map((option, index) => (
          <button
            key={index}
            type="button"
            className={index === recommended ? "button primary option" : "button option"}
            ref={index === recommended ? recommendedButton : undefined}
            disabled={busy}
            data-recommended={index === recommended ? "true" : undefined}
            onClick={() => send({ kind: "option", index })}
          >
            <span>{words.option(letterOf(index), option)}</span>
            {index === recommended ? <span className="option-mark">{words.recommended}</span> : null}
          </button>
        ))}
      </div>
      <p className="quiet">{recommended === null ? words.noRecommendation : words.enterHint}</p>
      <form className="question-own" onSubmit={submitOwn}>
        <label htmlFor={`${id}-own`}>{words.own}</label>
        <div className="row wrap">
          <input id={`${id}-own`} value={own} disabled={busy} onChange={(event) => setOwn(event.target.value)} />
          <button type="submit" className="button" disabled={busy || ownAnswer === null}>
            {own.trim() === "" && recommended !== null ? words.acceptRecommended : words.sendOwn}
          </button>
        </div>
      </form>
      {busy ? (
        <p className="quiet" role="status">
          {words.busy}
        </p>
      ) : null}
    </section>
  );
}
