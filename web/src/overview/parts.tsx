/**
 * Small pieces the Overview and the chat's side rail share: a sentence built from parts, the
 * "who is doing what" list, a file's kind icon and the section frame with its loading states.
 */
import type { ReactNode } from "react";
import { ArrowRight, CircleDot, Eye, File, FileCode, FileText, Globe, Image, Music, OctagonAlert, Table, Video, type LucideIcon } from "lucide-react";
import { previewKind, type PreviewKind } from "../lib/files";
import type { Loaded } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { story, type Part } from "../strings.overview";
import { Skeleton } from "../ui/Skeleton";
import type { NowEntry, NowStatus } from "./now";
import { AgentAvatar } from "../crew/names";

/** Names in bold; titles written by agents or people as plain text (P4). */
export function Sentence({ parts }: { parts: readonly Part[] }): JSX.Element {
  return (
    <>
      {parts.map((part, index) => {
        if (typeof part === "string") return <span key={index}>{part}</span>;
        if ("who" in part) return <strong key={index} className="ov-who">{part.who}</strong>;
        return <AgentText key={index} className="ov-title" text={part.title} />;
      })}
    </>
  );
}

const AVATAR_STATUS: Record<NowStatus, "working" | "waiting" | "blocked" | "idle"> = {
  working: "working",
  blocked: "blocked",
  review: "waiting",
  checking: "waiting",
  claimed: "idle",
};

function NowMark({ entry }: { entry: NowEntry }): JSX.Element {
  if (entry.seat) return <AgentAvatar seat={entry.seat} size="sm" status={AVATAR_STATUS[entry.status]} />;
  const Icon = entry.status === "blocked" ? OctagonAlert : entry.status === "review" ? Eye : CircleDot;
  return (
    <span className={`ov-mark mark-${entry.status}`} aria-hidden="true">
      <Icon size={14} />
    </span>
  );
}

export function NowList({
  entries,
  limit,
  onMore,
  compact = false,
}: {
  entries: NowEntry[];
  limit?: number;
  onMore?(): void;
  compact?: boolean;
}): JSX.Element {
  if (entries.length === 0) return <p className="quiet ov-quiet-line">{story.now.empty}</p>;
  const shown = limit ? entries.slice(0, limit) : entries;
  const rest = entries.length - shown.length;
  return (
    <>
      <ul className={`plain ov-now${compact ? " compact" : ""}`} aria-label={story.now.label}>
        {shown.map((entry) => (
          <li key={entry.key} className={`ov-now-item status-${entry.status}`}>
            <NowMark entry={entry} />
            <span className="ov-now-text">
              <span className="ov-now-line">
                <Sentence parts={entry.parts} />
              </span>
              {entry.note ? (
                entry.noteIsAgentText ? (
                  <AgentText className="ov-now-note" text={entry.note} />
                ) : (
                  <span className="ov-now-note">{entry.note}</span>
                )
              ) : null}
            </span>
          </li>
        ))}
      </ul>
      {rest > 0 && onMore ? (
        <button type="button" className="button ghost small ov-more" onClick={onMore}>
          {story.now.more(rest)}
          <ArrowRight size={14} aria-hidden="true" />
        </button>
      ) : null}
    </>
  );
}

const FILE_ICONS: Record<PreviewKind, LucideIcon> = {
  markdown: FileText,
  text: FileText,
  pdf: FileText,
  html: Globe,
  csv: Table,
  image: Image,
  code: FileCode,
  audio: Music,
  video: Video,
  none: File,
};

/** A kind icon for a file, from its name and media type. */
export function FileIcon({ name, mediaType, size = 16 }: { name: string; mediaType: string | null; size?: number }): JSX.Element {
  const Icon = FILE_ICONS[previewKind(name, mediaType)];
  return <Icon size={size} aria-hidden="true" />;
}

/** The loading, error and loaded states each part of the page shares. */
export function Load<T>({ load, lines = 3, children }: { load: Loaded<T>; lines?: number; children(data: T): ReactNode }): JSX.Element {
  if (load.data !== undefined) return <>{children(load.data)}</>;
  if (load.error) {
    return (
      <div className="ov-error" role="alert">
        <p className="quiet">{story.sectionError}</p>
        <button type="button" className="button small" onClick={load.reload}>
          {story.retry}
        </button>
      </div>
    );
  }
  return <Skeleton lines={lines} />;
}

export function More({ label, onClick }: { label: string; onClick(): void }): JSX.Element {
  return (
    <button type="button" className="button ghost small ov-more" onClick={onClick}>
      {label}
      <ArrowRight size={14} aria-hidden="true" />
    </button>
  );
}
