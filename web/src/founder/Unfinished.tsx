/** The person's unfinished drafting conversations, on the project list, so they can go on with one (FND-1). */
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";

export function Unfinished(): JSX.Element | null {
  const words = t.founder.way;
  const draftings = useLoad(() => get("/v1/founder/list"), []);
  const open = (draftings.data?.items ?? []).filter((item) => item.state === "drafting");
  if (draftings.error) return <ErrorNote error={draftings.error} />;
  if (open.length === 0) return null;
  return (
    <section aria-labelledby="unfinished-title" data-testid="unfinished">
      <h2 id="unfinished-title">{words.unfinishedTitle}</h2>
      <ul className="project-list" aria-label={words.unfinishedList}>
        {open.map((item) => (
          <li key={item.drafting_id}>
            <Link to={`/draft/${item.drafting_id}`} className="project-link">
              <span className="project-name">
                {words.resume}
                <span className="visually-hidden"> {words.resumeOf(item.opening)}</span>
              </span>
              <span className="draft-opening">{item.opening}</span>
              {item.quick ? <span className="badge">{words.quickTag}</span> : null}
              <span className="quiet">{words.updated(formatDateTime(item.updated_at))}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
