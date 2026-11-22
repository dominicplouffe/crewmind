/** What was said in a drafting conversation (FND-1): the stored lines, and the Founder's reply as it is written. */
import { useEffect, useRef } from "react";
import { Markdown } from "../components/common";
import { formatDateTime, formatTime } from "../lib/format";
import { t } from "../strings";
import { Avatar } from "../ui/Avatar";
import type { Line } from "./logic";

interface Props {
  lines: Line[];
  /** The Founder's words so far, while it writes. */
  reply: string;
}

const SIDE: Record<string, string> = { person: "from-person", founder: "from-agent", platform: "is-status" };

function LineItem({ line }: { line: Line }): JSX.Element {
  const words = t.founder.talk;
  const author = words.authors[line.author] ?? line.author;
  const kind = (line.detail as { kind?: unknown } | null)?.kind;
  const side = SIDE[line.author] ?? "is-status";
  const head = (
    <header className="message-head">
      <span className="author">{author}</span>
      <time dateTime={line.at} title={formatDateTime(line.at)} className="message-time">
        {formatTime(line.at)}
      </time>
      {kind === "document" ? <span className="badge">{words.documentTag}</span> : null}
    </header>
  );
  return (
    <article
      className={`message ${side} ${side === "is-status" ? "is-row" : "is-bubble"}`}
      aria-label={words.lineLabel(author, formatDateTime(line.at))}
      data-testid={`line-${line.author}`}
    >
      {side === "from-agent" ? (
        <div className="message-gutter">
          <Avatar name={words.avatarName} kind="agent" size="md" />
        </div>
      ) : null}
      <div className="message-main">
        {head}
        <div className="message-content">
          <div className="body">
            <Markdown source={line.body} />
          </div>
        </div>
      </div>
    </article>
  );
}

export function Conversation({ lines, reply }: Props): JSX.Element {
  const words = t.founder.talk;
  const end = useRef<HTMLDivElement>(null);
  const shown = useRef(0);

  // New lines go in at the end: bring them into view, but not on the first load of a long conversation.
  useEffect(() => {
    if (shown.current > 0 && lines.length > shown.current) {
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      end.current?.scrollIntoView({ block: "nearest", behavior: calm ? "auto" : "smooth" });
    }
    shown.current = lines.length;
  }, [lines.length]);

  return (
    <div className="draft-lines" role="log" aria-live="polite" aria-label={words.logLabel}>
      {lines.map((line) => (
        <LineItem key={line.id} line={line} />
      ))}
      {reply ? (
        <article className="message from-agent is-bubble is-typing" aria-label={words.writingLabel} data-testid="founder-reply">
          <div className="message-gutter">
            <Avatar name={t.founder.talk.avatarName} kind="agent" size="md" status="working" />
          </div>
          <div className="message-main">
            <header className="message-head">
              <span className="author">{words.authors.founder ?? t.founder.talk.avatarName}</span>
              <span className="message-role">{words.writing}</span>
            </header>
            <div className="message-content">
              <div className="body">
                <Markdown source={reply} />
              </div>
            </div>
          </div>
        </article>
      ) : null}
      <div ref={end} />
    </div>
  );
}
