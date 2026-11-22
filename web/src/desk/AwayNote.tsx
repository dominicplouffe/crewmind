/** "Since you were away": what happened in a project while the person was gone, shown once when its chat opens. */
import { useEffect, useState } from "react";
import { post } from "../api/client";
import { t } from "../strings";
import { SectionLists } from "./Brief";
import { AWAY_SECTIONS, filledSections } from "./logic";

type Summary = Record<string, string[]>;

export function AwayNote({ projectId }: { projectId: string }): JSX.Element | null {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    let current = true;
    setSummary(null);
    post("/v1/chat/opened", { project_id: projectId })
      .then((result) => {
        // Opening is recorded by the first call, so a later call never says "away": only a yes is kept.
        if (current && result.away) setSummary(result.summary ?? {});
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [projectId]);

  if (summary === null) return null;
  const words = t.decisions.away;
  return (
    <section className="note away-note" aria-labelledby="away-title" data-testid="away-note">
      <h2 id="away-title" className="group-title">
        {words.title}
      </h2>
      {filledSections(summary, AWAY_SECTIONS).length === 0 ? <p className="quiet">{words.nothing}</p> : null}
      <SectionLists sections={summary} order={AWAY_SECTIONS} titles={words.sections} />
      <button type="button" className="link" onClick={() => setSummary(null)}>
        {t.common.dismiss}
        <span className="visually-hidden"> {words.title}</span>
      </button>
    </section>
  );
}
