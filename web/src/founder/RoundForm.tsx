/**
 * The round of questions the Founder is asking (FND-3, FND-4), as one form. Each question shows
 * its options with the recommended one already chosen, what the answer changes, and room for the
 * person's own words. Nothing is sent until the person sends the whole round.
 */
import { useId, useState, type FormEvent } from "react";
import { t } from "../strings";
import { answerFor, decisionName, firstChoice, letterOf, type Choice, type Question } from "./logic";

interface Props {
  questions: Question[];
  busy: boolean;
  /** Sends every answer of the round. Resolves true when the server took them all. */
  onSubmit(answers: { questionId: number; answer: string }[]): Promise<boolean>;
}

type Chosen = Record<number, Choice | null>;

function isOwn(choice: Choice | null | undefined): choice is { kind: "own"; text: string } {
  return choice?.kind === "own";
}

export function RoundForm({ questions, busy, onSubmit }: Props): JSX.Element {
  const words = t.founder.question;
  const id = useId();
  const [chosen, setChosen] = useState<Chosen>({});
  const choiceOf = (question: Question): Choice | null =>
    question.id in chosen ? (chosen[question.id] ?? null) : firstChoice(question);
  const choose = (question: Question, choice: Choice): void =>
    setChosen((before) => ({ ...before, [question.id]: choice }));

  const answers = questions.map((question) => {
    const choice = choiceOf(question);
    // "Something else" with nothing written is not an answer yet.
    const blank = isOwn(choice) && choice.text.trim() === "";
    return { questionId: question.id, answer: choice && !blank ? answerFor(question, choice) : null };
  });
  const unanswered = answers.filter((entry) => entry.answer === null).length;

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (busy || unanswered > 0) return;
    const ready = answers.map((entry) => ({ questionId: entry.questionId, answer: entry.answer ?? "" }));
    void onSubmit(ready).then((taken) => {
      if (taken) setChosen({});
    });
  };

  return (
    <form className="round" onSubmit={submit} aria-labelledby={`${id}-title`} data-testid="round">
      <header className="round-head">
        <h2 id={`${id}-title`}>{words.roundTitle(questions.length)}</h2>
        <p className="quiet">{words.roundIntro}</p>
      </header>
      {questions.map((question, position) => {
        const choice = choiceOf(question);
        const name = `${id}-q${question.id}`;
        return (
          <fieldset
            key={question.id}
            className="question-card"
            data-testid="question-card"
            data-settles={question.settles}
            disabled={busy}
          >
            <legend className="question-legend">
              <span className="question-count">{words.position(position + 1, questions.length)}</span>
              <span className="question-topic">{decisionName(question.settles)}</span>
            </legend>
            <p className="question-text">{question.text}</p>
            <p className="quiet" data-testid="question-changes">
              {words.changes(question.changes)}
            </p>
            <div className="question-options">
              {question.options.map((option, index) => {
                const picked = choice?.kind === "option" && choice.index === index;
                return (
                  <label key={index} className={picked ? "option picked" : "option"}>
                    <input
                      type="radio"
                      name={name}
                      checked={picked}
                      onChange={() => choose(question, { kind: "option", index })}
                    />
                    <span className="option-text">{words.option(letterOf(index), option)}</span>
                    {index === question.recommended ? <span className="option-mark">{words.recommended}</span> : null}
                  </label>
                );
              })}
              <label className={isOwn(choice) ? "option own picked" : "option own"}>
                <input
                  type="radio"
                  name={name}
                  checked={isOwn(choice)}
                  onChange={() => choose(question, { kind: "own", text: "" })}
                />
                <span className="option-text">{words.ownChoice}</span>
                <input
                  type="text"
                  className="own-text"
                  aria-label={words.own}
                  placeholder={words.ownPlaceholder}
                  value={isOwn(choice) ? choice.text : ""}
                  onFocus={() => {
                    if (!isOwn(choice)) choose(question, { kind: "own", text: "" });
                  }}
                  onChange={(event) => choose(question, { kind: "own", text: event.target.value })}
                />
              </label>
            </div>
            {question.recommended === null && choice === null ? (
              <p className="quiet">{words.noRecommendation}</p>
            ) : null}
          </fieldset>
        );
      })}
      <footer className="round-foot">
        <button type="submit" className="button primary large" disabled={busy || unanswered > 0}>
          {busy ? words.submitting : words.submit(questions.length)}
        </button>
        {unanswered > 0 ? (
          <span className="quiet" role="status">
            {words.unanswered(unanswered)}
          </span>
        ) : null}
      </footer>
    </form>
  );
}
