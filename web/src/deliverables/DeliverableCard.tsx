/**
 * One file as a card: a real preview, its name, status, versions, who made it and when (ART-3).
 * The name is the button; it stretches over the whole card so the card is one target.
 */
import { Lock } from "lucide-react";
import type { Artifact } from "../api/client";
import { fromNow } from "../lib/humanize";
import { deliverables as words } from "../strings.crew";
import { Avatar } from "../ui/Avatar";
import { Pill, type Tone } from "../ui/Status";
import type { AuthorKind } from "./logic";
import { Thumb } from "./Thumb";

const STATUS_TONE: Record<string, Tone> = { draft: "neutral", "in review": "info", verified: "accent", delivered: "success" };

export function statusWord(status: string): string {
  return words.status[status] ?? status;
}

export function madeBy(item: Artifact, author: AuthorKind, me: string | undefined): string {
  if (author === "platform") return words.writtenByPlatform;
  const who = me && item.last_author === me ? words.you : item.last_author;
  return item.kind === "upload" ? words.uploadedBy(who) : words.madeBy(who);
}

interface Props {
  projectId: string;
  item: Artifact;
  author: AuthorKind;
  me: string | undefined;
  compact?: boolean;
  onOpen(): void;
}

export function DeliverableCard({ projectId, item, author, me, compact = false, onOpen }: Props): JSX.Element {
  const made = madeBy(item, author, me);
  return (
    <article className={`deliv-card${compact ? " compact" : ""}`} data-testid="deliverable">
      <Thumb projectId={projectId} item={item} />
      <div className="deliv-body">
        <h3 className="deliv-name">
          <button type="button" className="deliv-open" onClick={onOpen} title={item.name} aria-label={words.open(item.name)}>
            {item.name}
          </button>
        </h3>
        <div className="deliv-tags">
          <Pill tone={STATUS_TONE[item.status] ?? "neutral"}>{statusWord(item.status)}</Pill>
          {!compact ? <span className="badge">{words.kinds[item.kind] ?? item.kind}</span> : null}
          {item.versions > 1 ? <span className="badge tabular">{words.versions(item.versions)}</span> : null}
          {item.locked ? (
            <span className="badge">
              <Lock size={11} aria-hidden="true" />
              {words.locked}
            </span>
          ) : null}
          {item.superseded_by ? <span className="badge">{words.superseded}</span> : null}
        </div>
        <p className="deliv-meta">
          {author === "platform" ? null : (
            <Avatar name={item.last_author} kind={author === "agent" ? "agent" : "person"} size="xs" />
          )}
          <span className="deliv-meta-text">
            {made}
            <span aria-hidden="true"> · </span>
            <time dateTime={item.last_change}>{fromNow(item.last_change)}</time>
          </span>
        </p>
      </div>
    </article>
  );
}
