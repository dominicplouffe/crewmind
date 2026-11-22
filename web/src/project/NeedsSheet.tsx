/** What waits on the person in this project, as decision cards in a sheet, from the one desk list. */
import { CheckCircle2 } from "lucide-react";
import { InboxItem } from "../home/InboxItem";
import type { DeskEntry } from "../needs/summary";
import { home, projectLayout } from "../strings.shell";
import { Sheet } from "../ui/Sheet";

interface Props {
  projectName: string;
  entries: DeskEntry[];
  onClose(): void;
  onChanged(): void;
}

export function NeedsSheet({ projectName, entries, onClose, onChanged }: Props): JSX.Element {
  return (
    <Sheet title={projectLayout.needsYou(entries.length)} subtitle={projectName} onClose={onClose} size="lg" testId="needs-sheet">
      {entries.length === 0 ? (
        <div className="empty">
          <span className="empty-icon success" aria-hidden="true">
            <CheckCircle2 size={22} />
          </span>
          <p className="empty-title">{home.inboxEmptyTitle}</p>
          <p className="quiet">{projectLayout.railNeedsEmpty}</p>
        </div>
      ) : (
        <ul className="plain inbox-list" aria-label={home.inboxLabel}>
          {entries.map((entry, index) => (
            <InboxItem key={entry.item ? `item-${entry.item.id}` : `${entry.what}-${index}`} entry={entry} onChanged={onChanged} showProject={false} />
          ))}
        </ul>
      )}
    </Sheet>
  );
}
