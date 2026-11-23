/**
 * The crew in one row: avatars with status dots and a count by status (CHAT-18). The whole strip
 * is one button that opens the crew.
 */
import { ChevronRight } from "lucide-react";
import type { Header } from "../api/client";
import { crew, overview } from "../strings.crew";
import { useCrew } from "./data";
import { SUMMARY_ORDER, statusCounts, type CrewMember } from "./logic";
import { StatusFace } from "./parts";

/** How many faces the strip shows before "+N". */
const SHOWN = 6;
/** Runs from this window are enough to tell who is working or up next. */
const RECENT_HOURS = 24;
const ORDER: Record<CrewMember["status"], number> = { working: 0, blocked: 1, holding: 2, review: 3, waiting: 4, idle: 5 };

interface Props {
  projectId: string;
  changes: number;
  header: Header | null;
  onOpen(): void;
}

function ordered(members: CrewMember[]): CrewMember[] {
  const ceoFirst = (member: CrewMember): number => (member.kind === "ceo" ? 0 : 1);
  return members
    .filter((member) => member.state !== "stood down")
    .sort((a, b) => ceoFirst(a) - ceoFirst(b) || ORDER[a.status] - ORDER[b.status] || a.name.localeCompare(b.name));
}

export function CrewStrip({ projectId, changes, header, onOpen }: Props): JSX.Element {
  const data = useCrew(projectId, changes, header, RECENT_HOURS);
  if (!data.members && data.error) {
    return (
      <div className="crew-strip is-error" role="alert">
        <span className="quiet">{overview.sectionError}</span>
        <button type="button" className="button small" onClick={data.reload}>
          {overview.retry}
        </button>
      </div>
    );
  }
  if (!data.members) {
    return (
      <div className="crew-strip is-loading" aria-busy="true">
        <span className="visually-hidden" role="status">
          {crew.loading}
        </span>
        {[0, 1, 2].map((index) => (
          <span key={index} className="skeleton crew-strip-skel" aria-hidden="true" />
        ))}
      </div>
    );
  }
  const members = ordered(data.members);
  const counts = statusCounts(members);
  const summary = members.length ? crew.summary(SUMMARY_ORDER.map((status) => ({ status, count: counts[status] }))) : crew.emptyTitle;
  const extra = members.length - SHOWN;
  return (
    <button type="button" className="crew-strip" onClick={onOpen} data-testid="crew-strip">
      <span className="crew-strip-faces" aria-hidden="true">
        {members.slice(0, SHOWN).map((member) => (
          <span key={member.name} className="crew-strip-face" title={`${member.name}: ${member.label}`}>
            <StatusFace name={member.name} size="sm" status={member.status} />
          </span>
        ))}
        {extra > 0 ? <span className="crew-strip-more">{crew.stripMore(extra)}</span> : null}
      </span>
      <span className="visually-hidden">{crew.stripBefore}</span>
      <span className="crew-strip-summary tabular">{summary}</span>
      <span className="visually-hidden">{crew.stripAfter}</span>
      <ChevronRight className="crew-strip-chevron" size={16} aria-hidden="true" />
    </button>
  );
}
