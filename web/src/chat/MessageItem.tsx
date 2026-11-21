/** One stored chat message: author, reply quote, body, action card or upload link, and its actions. */
import { memo, useState } from "react";
import type { Card, Message, Order, ReopenRequest } from "../api/client";
import { Markdown } from "../components/common";
import { formatDateTime, formatTime } from "../lib/format";
import { t } from "../strings";
import { ActionCard } from "./ActionCard";
import { Markers, StatusActions, detailOf } from "./MessageExtras";
import { MessageMenu, type MenuAction } from "./MessageMenu";
import type { ListeningHandlers } from "./useListening";

/** Agent messages longer than this fold behind "Show more" (display only). */
const FOLD_CHARS = 1500;
const FOLD_LINES = 24;
const QUOTE_CHARS = 120;

export interface MessageHandlers extends ListeningHandlers {
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
  /** The proposed order or reopen request this status line is about, when it has one. */
  order?: Order;
  request?: ReopenRequest;
  /** An example mark set or removed on this page; otherwise the message's own detail says. */
  example?: boolean;
}

function isLong(body: string): boolean {
  return body.length > FOLD_CHARS || body.split("\n").length > FOLD_LINES;
}

export function snippet(body: string): string {
  const line = body.replace(/\s+/g, " ").trim();
  return line.length > QUOTE_CHARS ? `${line.slice(0, QUOTE_CHARS)}…` : line;
}

/** The less common actions (CHAT-8). Which of them the server allows is the server's rule, not this list's. */
function menuActions(message: Message, isExample: boolean, handlers: MessageHandlers): MenuAction[] {
  if (message.author_kind === "agent" && message.kind === "message") {
    return [{ key: "fix", label: t.listening.fix, run: () => handlers.onFix(message) }];
  }
  if (message.author_kind !== "person") return [];
  const example: MenuAction = isExample
    ? { key: "unmark", label: t.listening.unmarkExample, run: () => handlers.onExample(message, false) }
    : { key: "mark", label: t.listening.markExample, run: () => handlers.onExample(message, true) };
  if (message.kind !== "message") return [example];
  return [
    { key: "pin", label: t.listening.pin, run: () => handlers.onPin(message) },
    example,
    { key: "decide", label: t.listening.decide, run: () => handlers.onDecide(message) },
  ];
}

function MessageItemInner({ message, parent, card, replies, handlers, compact, order, request, example }: Props): JSX.Element {
  const detail = detailOf(message);
  const foldable = message.author_kind === "agent" && isLong(message.body);
  const [open, setOpen] = useState(false);
  const isStatus = message.kind === "status";
  const threadId = message.thread_id ?? (replies > 0 ? message.id : null);
  const isExample = example ?? (message.example === true || detail.kind === "example");

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
        <Markers detail={detail} example={isExample} />
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
      {isStatus ? <StatusActions detail={detail} order={order} request={request} handlers={handlers} /> : null}
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
        {!compact ? <MessageMenu author={message.author} actions={menuActions(message, isExample, handlers)} /> : null}
      </div>
    </article>
  );
}

export const MessageItem = memo(MessageItemInner);
