/** What was said in a drafting conversation (FND-1): the stored lines, and the Founder's reply as it is written. */
import { useEffect, useRef } from "react";
import { Markdown } from "../components/common";
import { formatDateTime, formatTime } from "../lib/format";
import { t } from "../strings";
import { Avatar } from "../ui/Avatar";
import type { Line } from "./logic";
import { WorkingLine } from "./WorkingLine";

interface Props {
  lines: Line[];
  /** The Founder's words so far, while it writes. */
  reply: string;
  /** The Founder owes a turn and has not started writing: what it is doing, and since when (P17). */
  thinking?: { doing: string; since: string } | null;
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

export function Conversation({ lines, reply, thinking = null }: Props): JSX.Element {
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

  // When the Founder starts working, bring its bubble into view: the person sees it took the message.
  const working = thinking !== null;
  useEffect(() => {
    if (working) end.current?.scrollIntoView({ block: "nearest" });
  }, [working]);

  return (
    <div className="draft-lines" role="log" aria-live="polite" aria-label={words.logLabel}>
      {lines.map((line) => (
        <LineItem key={line.id} line={line} />
      ))}
      {reply || thinking ? (
        // One bubble for the whole turn: its dots move for as long as the Founder owes the turn, its
        // words appear as they are written, and what it is doing shows under them (P17).
        <article
          className={reply ? "message from-agent is-bubble is-typing" : "message from-agent is-bubble is-typing is-thinking"}
          aria-label={reply ? words.writingLabel : words.thinkingLabel}
          data-testid={reply ? "founder-reply" : "founder-thinking"}
        >
          <div className="message-gutter">
            <Avatar name={t.founder.talk.avatarName} kind="agent" size="md" status={thinking ? "working" : null} />
          </div>
          <div className="message-main">
            <header className="message-head">
              <span className="author">{words.authors.founder ?? t.founder.talk.avatarName}</span>
              <span className="message-role typing-doing">
                {thinking ? (
                  <span className="typing-dots" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </span>
                ) : null}
                {reply ? words.writingNow : words.thinking}
              </span>
            </header>
            <div className="message-content">
              {reply ? (
                <div className="body">
                  <Markdown source={reply} />
                </div>
              ) : null}
              {thinking && (!reply || thinking.doing) ? <WorkingLine doing={thinking.doing} since={thinking.since} /> : null}
            </div>
          </div>
        </article>
      ) : null}
      <div ref={end} />
    </div>
  );
}
