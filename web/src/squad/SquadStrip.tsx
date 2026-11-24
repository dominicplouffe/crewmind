/**
 * The squad in one row: avatars with status dots and a count by status (CHAT-18). The whole strip
 * is one button that opens the squad.
 */
import { ChevronRight } from "lucide-react";
import type { Header } from "../api/client";
import { squad, overview } from "../strings.squad";
import { useSquad } from "./data";
import { SUMMARY_ORDER, statusCounts, type SquadMember } from "./logic";
import { StatusFace } from "./parts";

/** How many faces the strip shows before "+N". */
const SHOWN = 6;
/** Runs from this window are enough to tell who is working or up next. */
const RECENT_HOURS = 24;
const ORDER: Record<SquadMember["status"], number> = { working: 0, blocked: 1, holding: 2, review: 3, waiting: 4, idle: 5 };

interface Props {
  projectId: string;
  changes: number;
  header: Header | null;
  onOpen(): void;
}

function ordered(members: SquadMember[]): SquadMember[] {
  const ceoFirst = (member: SquadMember): number => (member.kind === "ceo" ? 0 : 1);
  return members
    .filter((member) => member.state !== "stood down")
    .sort((a, b) => ceoFirst(a) - ceoFirst(b) || ORDER[a.status] - ORDER[b.status] || a.displayName.localeCompare(b.displayName));
}

export function SquadStrip({ projectId, changes, header, onOpen }: Props): JSX.Element {
  const data = useSquad(projectId, changes, header, RECENT_HOURS);
  if (!data.members && data.error) {
    return (
      <div className="squad-strip is-error" role="alert">
        <span className="quiet">{overview.sectionError}</span>
        <button type="button" className="button small" onClick={data.reload}>
          {overview.retry}
        </button>
      </div>
    );
  }
  if (!data.members) {
    return (
      <div className="squad-strip is-loading" aria-busy="true">
        <span className="visually-hidden" role="status">
          {squad.loading}
        </span>
        {[0, 1, 2].map((index) => (
          <span key={index} className="skeleton squad-strip-skel" aria-hidden="true" />
        ))}
      </div>
    );
  }
  const members = ordered(data.members);
  const counts = statusCounts(members);
  const summary = members.length ? squad.summary(SUMMARY_ORDER.map((status) => ({ status, count: counts[status] }))) : squad.emptyTitle;
  const extra = members.length - SHOWN;
  return (
    <button type="button" className="squad-strip" onClick={onOpen} data-testid="squad-strip">
      <span className="squad-strip-faces" aria-hidden="true">
        {members.slice(0, SHOWN).map((member) => (
          <span key={member.name} className="squad-strip-face" title={`${member.displayName}, ${member.roleLabel}: ${member.label}`}>
            <StatusFace seat={member.name} size="sm" status={member.status} />
          </span>
        ))}
        {extra > 0 ? <span className="squad-strip-more">{squad.stripMore(extra)}</span> : null}
      </span>
      <span className="visually-hidden">{squad.stripBefore}</span>
      <span className="squad-strip-summary tabular">{summary}</span>
      <span className="visually-hidden">{squad.stripAfter}</span>
      <ChevronRight className="squad-strip-chevron" size={16} aria-hidden="true" />
    </button>
  );
}
