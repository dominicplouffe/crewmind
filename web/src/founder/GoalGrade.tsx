/** The grade of each element of the goal (FND-6, FND-7), with its quoted line, the reason and the fix. */
import { t } from "../strings";
import { elementName, type Grade } from "./logic";

export function GoalGrade({ grade }: { grade: Grade }): JSX.Element {
  const words = t.founder.side;
  return (
    <ul className="records plain" data-testid="goal-grade">
      {grade.elements.map((element) => (
        <li key={element.element} data-testid="grade-element" data-grade={element.grade}>
          <p className="row wrap">
            <span className="record-text">{elementName(element.element)}</span>
            <span className={`badge grade-${element.grade}`}>{words.grades[element.grade] ?? element.grade}</span>
          </p>
          {element.quote ? <blockquote className="quote">{element.quote}</blockquote> : null}
          {element.reason ? <p className="quiet">{words.reason(element.reason)}</p> : null}
          {element.fix ? <p>{words.fix(element.fix)}</p> : null}
        </li>
      ))}
    </ul>
  );
}
