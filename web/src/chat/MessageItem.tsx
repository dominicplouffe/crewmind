/** One stored chat message: author, reply quote, body, action card or upload link, and its actions. */
import { memo, useState } from "react";
import type { Card, Message } from "../api/client";
import { Markdown } from "../components/common";
import { formatDateTime, formatTime } from "../lib/format";
import { t } from "../strings";
import { ActionCard } from "./ActionCard";

/** Agent messages longer than this fold behind "Show more" (display only). */
const FOLD_CHARS = 1500;
const FOLD_LINES = 24;
const QUOTE_CHARS = 120;

export interface MessageHandlers {
  onReply(message: Message): void;
  onThread(threadId: number): void;
  onJump(messageId: number): void;
  onPreview(name: string): void;
  onTrace(runId: string): void;
  onAccept(cardId: number, edited?: string): Promise<void>;
  onDismiss(cardId: number): Promise<void>;
}

interface Props {
  message: Message;
  parent: Message | undefined;
  card: Card | undefined;
  replies: number;
  handlers: MessageHandlers;
  compact?: boolean;
}

function isLong(body: string): boolean {
  return body.length > FOLD_CHARS || body.split("\n").length > FOLD_LINES;
}

export function snippet(body: string): string {
  const line = body.replace(/\s+/g, " ").trim();
  return line.length > QUOTE_CHARS ? `${line.slice(0, QUOTE_CHARS)}…` : line;
}

function detailOf(message: Message): { kind: string; card?: number; artifact?: string } {
  const detail = message.detail as { kind?: unknown; card?: unknown; artifact?: unknown } | null;
  return {
    kind: typeof detail?.kind === "string" ? detail.kind : "",
    card: typeof detail?.card === "number" ? detail.card : undefined,
    artifact: typeof detail?.artifact === "string" ? detail.artifact : undefined,
  };
}

function MessageItemInner({ message, parent, card, replies, handlers, compact }: Props): JSX.Element {
  const detail = detailOf(message);
  const foldable = message.author_kind === "agent" && isLong(message.body);
  const [open, setOpen] = useState(false);
  const isStatus = message.kind === "status";
  const threadId = message.thread_id ?? (replies > 0 ? message.id : null);

  return (
    <article
      id={compact ? undefined : `message-${message.id}`}
      className={`message from-${message.author_kind} ${isStatus ? "is-status" : ""}`}
      tabIndex={-1}
      aria-label={t.chat.messageLabel(message.author, formatDateTime(message.at))}
      data-testid={`message-${message.author_kind}`}
    >
      <header className="message-head">
        <span className="author">{message.author}</span>
        <span className="kind-tag">{t.chat.authorKinds[message.author_kind as "person" | "agent" | "platform"] ?? ""}</span>
        <time dateTime={message.at} title={formatDateTime(message.at)}>
          {formatTime(message.at)}
        </time>
        {message.author_kind === "person" && !isStatus ? (
          <span className="tick" data-testid="delivered">
            <span aria-hidden="true">✓</span> {t.chat.delivered}
          </span>
        ) : null}
      </header>
      {parent && !compact ? (
        <button type="button" className="reply-quote" onClick={() => handlers.onJump(parent.id)}>
          <span className="visually-hidden">{t.chat.jumpToParent} </span>
          {t.chat.inReplyTo(parent.author)} <q>{snippet(parent.body)}</q>
        </button>
      ) : null}
      {detail.kind === "action card" && detail.card !== undefined ? (
        <ActionCard card={card} onAccept={handlers.onAccept} onDismiss={handlers.onDismiss} />
      ) : (
        <div className={foldable && !open ? "body folded" : "body"}>
          <Markdown source={message.body} />
        </div>
      )}
      {foldable ? (
        <button type="button" className="link" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? t.chat.showLess : t.chat.showMore}
        </button>
      ) : null}
      <div className="message-actions">
        {detail.kind === "upload" && detail.artifact ? (
          <button type="button" className="link" onClick={() => handlers.onPreview(detail.artifact ?? "")}>
            {t.chat.preview(detail.artifact)}
          </button>
        ) : null}
        {!isStatus && !compact ? (
          <button type="button" className="link" onClick={() => handlers.onReply(message)}>
            {t.chat.reply}
            <span className="visually-hidden"> {t.chat.toAuthor(message.author)}</span>
          </button>
        ) : null}
        {threadId !== null && !compact ? (
          <button type="button" className="link" onClick={() => handlers.onThread(threadId)}>
            {replies > 0 ? t.chat.threadCount(replies) : t.chat.thread}
          </button>
        ) : null}
        {message.run_id ? (
          <button type="button" className="link" onClick={() => handlers.onTrace(message.run_id ?? "")}>
            {t.chat.trace}
            <span className="visually-hidden"> {t.chat.traceOf(message.author)}</span>
          </button>
        ) : null}
      </div>
    </article>
  );
}

export const MessageItem = memo(MessageItemInner);
