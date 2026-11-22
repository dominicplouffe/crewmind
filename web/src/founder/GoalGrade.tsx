/** The grade of the draft's goal (FND-6, FND-7): the summary, and each element with its quoted line and fix. */
import { t } from "../strings";
import { elementName, type Grade } from "./logic";

export function GoalGrade({ grade }: { grade: Grade | null }): JSX.Element {
  const words = t.founder.side;
  return (
    <section className="side-part" aria-labelledby="grade-title" data-testid="goal-grade">
      <h2 id="grade-title">{words.grade}</h2>
      {grade ? (
        <>
          <p className="row wrap">
            <span className={grade.ready ? "marker grade-present" : "marker grade-missing"}>
              {grade.ready ? words.gradeReady : words.gradeNotReady}
            </span>
            <span data-testid="grade-summary">{grade.summary}</span>
          </p>
          <ul className="records plain">
            {grade.elements.map((element) => (
              <li key={element.element} data-testid="grade-element" data-grade={element.grade}>
                <p className="row wrap">
                  <span className="record-text">{elementName(element.element)}</span>
                  <span className={`marker grade-${element.grade}`}>{words.grades[element.grade] ?? element.grade}</span>
                </p>
                {element.quote ? <blockquote className="quote">{element.quote}</blockquote> : null}
                {element.reason ? <p className="quiet">{words.reason(element.reason)}</p> : null}
                {element.fix ? <p>{words.fix(element.fix)}</p> : null}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="quiet">{words.gradeEmpty}</p>
      )}
    </section>
  );
}
