/**
 * What the drafted crew needs from outside (FND-9, CON-14): each secret, variable or MCP server,
 * whether you have it, and whether creating the project attaches it. A missing one links to
 * Connections, in a new tab so the conversation stays where it is.
 */
import { t } from "../strings";
import type { Drafting } from "./logic";

type Need = NonNullable<Drafting["needs"]>[number];

function status(need: Need): { text: string; tone: string } {
  const words = t.founder.needs;
  if (!need.have) return { text: words.missing, tone: "grade-missing" };
  return need.granted
    ? { text: words.attached, tone: "grade-present" }
    : { text: words.notGranted, tone: "grade-weak" };
}

export function DraftNeeds({ needs }: { needs: Need[] }): JSX.Element | null {
  const words = t.founder.needs;
  if (needs.length === 0) return null;
  const missing = needs.some((need) => !need.have);
  return (
    <section
      className="side-part"
      aria-labelledby="draft-needs-title"
      data-testid="draft-needs"
    >
      <h2 id="draft-needs-title">{words.title}</h2>
      <p className="quiet">{words.intro}</p>
      <ul className="checklist">
        {needs.map((need) => {
          const shown = status(need);
          return (
            <li
              key={`${need.kind}:${need.name}`}
              data-testid="draft-need"
              data-have={need.have}
            >
              <strong>{need.name}</strong>{" "}
              <span className="quiet">
                {words.line(words.kinds[need.kind] ?? need.kind, need.roles)}
              </span>{" "}
              <span className={`badge ${shown.tone}`}>{shown.text}</span>
            </li>
          );
        })}
      </ul>
      {missing ? (
        <p>
          <a
            href="/settings/connections"
            target="_blank"
            rel="noopener noreferrer"
          >
            {words.add}
            <span className="visually-hidden"> {words.newTab}</span>
          </a>{" "}
          <span className="quiet">{words.addAfter}</span>
        </p>
      ) : null}
    </section>
  );
}
