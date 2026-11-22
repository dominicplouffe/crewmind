/** The link to the Desk, with how many things wait on the person. */
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";

interface Props {
  /** Changes whenever something changed that may add to or clear the Desk, so the count reloads. */
  changes?: number;
}

export function DeskLink({ changes = 0 }: Props): JSX.Element {
  const desk = useLoad(() => get("/v1/desk/show"), [changes]);
  const count = desk.data?.waiting.length;
  return (
    <Link to="/desk" className="button small" data-testid="desk-link">
      {count === undefined ? (
        t.decisions.desk.linkPlain
      ) : (
        <>
          <span aria-hidden="true">{t.decisions.desk.link(count)}</span>
          <span className="visually-hidden">{t.decisions.desk.linkLabel(count)}</span>
        </>
      )}
    </Link>
  );
}
