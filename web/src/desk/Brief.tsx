/** The daily brief: per project, what is worth a look, what moved and what happens next. */
import { Newspaper } from "lucide-react";
import { useId } from "react";
import { Link } from "react-router-dom";
import type { Schemas } from "../api/client";
import { Empty } from "../panels/kit";
import { formatDateTime } from "../lib/format";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { BRIEF_SECTIONS, filledSections } from "./logic";

interface BriefProject {
  project_id?: unknown;
  name?: unknown;
  state?: unknown;
  sections?: unknown;
}

/** Titled lists; a list with nothing in it is left out. */
export function SectionLists({
  sections,
  order,
  titles,
}: {
  sections: unknown;
  order: readonly string[];
  titles: Record<string, string>;
}): JSX.Element {
  const id = useId();
  return (
    <>
      {filledSections(sections, order).map((section, index) => (
        <div key={section.name} data-testid="brief-section">
          <p className="eyebrow brief-section-title" id={`${id}-${index}`}>
            {titles[section.name] ?? section.name}
          </p>
          <ul aria-labelledby={`${id}-${index}`}>
            {section.lines.map((line, at) => (
              <li key={at}>
                <AgentText text={line} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

export function Brief({ brief }: { brief: Schemas["Brief"] }): JSX.Element {
  const words = t.decisions.brief;
  const projects = brief.projects as BriefProject[];
  return (
    <section aria-labelledby="brief-title" data-testid="brief">
      <h2 id="brief-title">{words.title}</h2>
      <p className="quiet">{words.period(formatDateTime(brief.since), formatDateTime(brief.until))}</p>
      {projects.length === 0 ? <Empty icon={Newspaper} title={words.emptyTitle} next={words.emptyNext} /> : null}
      {projects.map((project) => {
        const projectId = String(project.project_id ?? "");
        const filled = filledSections(project.sections, BRIEF_SECTIONS).length > 0;
        return (
          <article key={projectId} className="desk-group brief-project" data-testid="brief-project">
            <h3 className="group-title">
              <Link to={`/projects/${projectId}`}>{String(project.name ?? projectId)}</Link>
            </h3>
            {typeof project.state === "string" ? (
              <p className="quiet">
                <span className="badge">{words.projectState(project.state)}</span>
              </p>
            ) : null}
            {filled ? (
              <SectionLists sections={project.sections} order={BRIEF_SECTIONS} titles={words.sections} />
            ) : (
              <p className="quiet">{words.quiet}</p>
            )}
          </article>
        );
      })}
    </section>
  );
}
