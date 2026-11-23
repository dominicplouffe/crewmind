/**
 * The project's story, newest first and grouped by day (CHAT-19): who did what, named. Each line
 * has the actor's avatar, or an icon for the kind of event when no one in particular did it.
 */
import {
  Ban,
  CircleCheck,
  FileText,
  Flag,
  Gauge,
  Inbox,
  ListChecks,
  OctagonAlert,
  Pause,
  Play,
  Scale,
  Users,
  type LucideIcon,
} from "lucide-react";
import { story } from "../strings.overview";
import { Avatar } from "../ui/Avatar";
import { plainText } from "./now";
import { Sentence } from "./parts";
import type { StoryDay, StoryKind } from "./timeline";

const ICONS: Record<StoryKind, LucideIcon> = {
  project: Play,
  finished: CircleCheck,
  blocked: OctagonAlert,
  delivered: FileText,
  updated: FileText,
  proposed: ListChecks,
  accepted: ListChecks,
  met: Flag,
  cut: Ban,
  declined: Ban,
  hired: Users,
  asked: Inbox,
  decided: Scale,
  hold: Pause,
  budget: Gauge,
};

/** `me` is the signed-in person's name, for the initials on their own lines ("You"). */
export function Timeline({ days, me }: { days: StoryDay[]; me?: string }): JSX.Element {
  if (days.length === 0) return <p className="quiet ov-quiet-line">{story.timeline.empty}</p>;
  return (
    <div className="ov-story">
      {days.map((day) => (
        <section key={day.key} className="ov-day" aria-label={day.label}>
          <h3 className="ov-day-label">{day.label}</h3>
          <ol className="plain ov-events">
            {day.entries.map((entry, index) => {
              const Icon = ICONS[entry.kind];
              // A time equal to the line above is kept for screen readers but not repeated on screen.
              const repeat = index > 0 && day.entries[index - 1]?.when === entry.when;
              return (
                <li key={entry.id} className={`ov-event kind-${entry.kind}`}>
                  <span className="ov-event-mark">
                    {entry.who ? (
                      <Avatar name={entry.who.kind === "person" ? (me ?? entry.who.name) : entry.who.name} kind={entry.who.kind} size="xs" />
                    ) : (
                      <span className="ov-event-icon" aria-hidden="true">
                        <Icon size={12} />
                      </span>
                    )}
                  </span>
                  <span className="ov-event-body">
                    <span className="ov-event-text" title={plainText(entry.parts)}>
                      <Sentence parts={entry.parts} />
                    </span>
                    {entry.details.length > 0 ? (
                      <span className="ov-event-details">{entry.details.join(" · ")}</span>
                    ) : null}
                  </span>
                  <time className={`ov-event-time tabular${repeat ? " visually-hidden" : ""}`} dateTime={entry.at}>
                    {entry.when}
                  </time>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}
