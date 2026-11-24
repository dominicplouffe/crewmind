/**
 * One stored chat message (CHAT-3, CHAT-7, CHAT-8): who wrote it, a reply quote, the body, an action
 * or decision card or upload link, and its actions. Agents and people get an avatar and a name;
 * crewmind's own lines are quiet rows; the less common actions sit in a toolbar shown on hover or focus.
 */
import {
  AlertTriangle,
  ArrowRightLeft,
  CheckCheck,
  CornerUpLeft,
  Eye,
  Info,
  MessagesSquare,
  Paperclip,
  RotateCcw,
  Scale,
  ScrollText,
  Send,
  Sparkles,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { memo, useState } from "react";
import type { Card, Message, Order, ReopenRequest } from "../api/client";
import { Markdown } from "../components/common";
import { isNote } from "../desk/headline";
import { ChatItemCard } from "../desk/ItemCard";
import { ChatItemNote } from "../desk/ItemNote";
import { formatDateTime } from "../lib/format";
import { t } from "../strings";
import { AgentAvatar, useAgentName } from "../crew/names";
import { ActionCard } from "./ActionCard";
import { Markers, StatusActions, detailOf, draftingLine, isReopenLine, type MessageDetail } from "./MessageExtras";
import { Avatar } from "../ui/Avatar";
import { MessageMenu, type MenuAction } from "./MessageMenu";
import { RelativeTime } from "./RelativeTime";
import type { ListeningHandlers } from "./useListening";

/** Agent messages longer than this fold behind "Show more" (display only). */
const FOLD_CHARS = 1500;
const FOLD_LINES = 24;
const QUOTE_CHARS = 120;
const ICON = 15;

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
  /** The signed-in person wrote it: their name shows as "You". */
  mine?: boolean;
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

/** The small icon in front of one of crewmind's own lines, by what the line is about. */
function systemIcon(detail: MessageDetail): LucideIcon {
  switch (detail.kind) {
    case "directive":
      return Send;
    case "decision item":
      return Scale;
    case "standing order proposed":
      return ScrollText;
    case "reopen request":
      return RotateCcw;
    case "upload":
      return Paperclip;
    case "example":
      return Sparkles;
    case "handoff":
      return ArrowRightLeft;
    default:
      return /flag|slow|stall|fail|wall|losing/.test(detail.kind) ? AlertTriangle : Info;
  }
}

function MessageItemInner({
  message,
  parent,
  card,
  replies,
  handlers,
  compact,
  order,
  request,
  example,
  mine,
}: Props): JSX.Element {
  const nameOf = useAgentName();
  // An agent is shown by the name it goes by, its role beside it (EXE-18); the stored author is its seat.
  const agent = message.author_kind === "agent" ? nameOf(message.author) : null;
  const author = agent?.name ?? message.author;
  const role = agent?.role;
  const parentAuthor = parent ? (parent.author_kind === "agent" ? nameOf(parent.author).name : parent.author) : "";
  const detail = detailOf(message);
  const foldable = message.author_kind === "agent" && isLong(message.body);
  const [open, setOpen] = useState(false);
  const isStatus = message.kind === "status";
  const threadId = message.thread_id ?? (replies > 0 ? message.id : null);
  const isExample = example ?? (message.example === true || detail.kind === "example");
  const hasActionCard = detail.kind === "action card" && detail.card !== undefined;
  const isItemLine = detail.kind === "decision item" && detail.item !== undefined && !isReopenLine(detail);
  // A heads-up or a flag tells rather than asks: a quiet note, not a card.
  const hasItemNote = isItemLine && isNote(detail.itemKind);
  const hasItemCard = isItemLine && !hasItemNote;
  const hasStatusActions = isStatus && (detail.kind === "standing order proposed" || isReopenLine(detail));
  const kind = message.author_kind as "person" | "agent" | "platform";
  // A plain line from crewmind (or a person's status line) is a quiet row; one that carries a card is a card.
  const layout =
    isStatus && !hasActionCard && !hasItemCard && !hasStatusActions ? "row" : kind === "platform" ? "system" : "bubble";
  const menu = compact ? [] : menuActions(message, isExample, handlers);

  const toolbar = (
    <div className="message-actions" role="group" aria-label={t.chat.actionsLabel(author)}>
      {detail.kind === "upload" && detail.artifact ? (
        <button type="button" className="message-action has-text" onClick={() => handlers.onPreview(detail.artifact ?? "")}>
          <Eye size={ICON} aria-hidden="true" />
          {t.chat.preview(detail.artifact)}
        </button>
      ) : null}
      {!isStatus && !compact ? (
        <button type="button" className="message-action" title={t.chat.reply} onClick={() => handlers.onReply(message)}>
          <CornerUpLeft size={ICON} aria-hidden="true" />
          <span className="visually-hidden">
            {t.chat.reply} {t.chat.toAuthor(author)}
          </span>
        </button>
      ) : null}
      {threadId !== null && !compact ? (
        <button
          type="button"
          className={replies > 0 ? "message-action has-text" : "message-action"}
          title={t.chat.thread}
          onClick={() => handlers.onThread(threadId)}
        >
          <MessagesSquare size={ICON} aria-hidden="true" />
          {replies > 0 ? t.chat.threadCount(replies) : <span className="visually-hidden">{t.chat.thread}</span>}
        </button>
      ) : null}
      {message.run_id ? (
        <button
          type="button"
          className="message-action"
          title={t.chat.trace}
          onClick={() => handlers.onTrace(message.run_id ?? "")}
        >
          <Workflow size={ICON} aria-hidden="true" />
          <span className="visually-hidden">
            {t.chat.trace} {t.chat.traceOf(author)}
          </span>
        </button>
      ) : null}
      {menu.length > 0 ? <MessageMenu author={author} actions={menu} /> : null}
    </div>
  );
  const hasTools =
    (detail.kind === "upload" && Boolean(detail.artifact)) ||
    (!isStatus && !compact) ||
    (threadId !== null && !compact) ||
    Boolean(message.run_id) ||
    menu.length > 0;

  const quote =
    parent && !compact ? (
      <button type="button" className="reply-quote" onClick={() => handlers.onJump(parent.id)}>
        <CornerUpLeft size={13} aria-hidden="true" />
        <span className="visually-hidden">{t.chat.jumpToParent} </span>
        <span className="reply-quote-text">
          {t.chat.inReplyTo(parentAuthor)} <q>{snippet(parent.body)}</q>
        </span>
      </button>
    ) : null;

  const content = hasActionCard ? (
    <ActionCard card={card} onAccept={handlers.onAccept} onDismiss={handlers.onDismiss} />
  ) : hasItemCard && detail.item !== undefined ? (
    <ChatItemCard itemId={detail.item} />
  ) : (
    <div className={foldable && !open ? "body folded" : "body"}>
      <Markdown source={message.body} />
    </div>
  );

  const article = (className: string, children: JSX.Element): JSX.Element => (
    <article
      id={compact ? undefined : `message-${message.id}`}
      className={`message from-${message.author_kind} ${isStatus ? "is-status" : ""} ${className}`}
      tabIndex={-1}
      aria-label={t.chat.messageLabel(author, formatDateTime(message.at))}
      data-testid={`message-${message.author_kind}`}
    >
      {children}
    </article>
  );

  // A line said while drafting, before the project existed: shown as said, by whom, and kept as a record.
  const drafted = draftingLine(message);
  if (drafted) {
    const byPerson = drafted.author === "person";
    const who = byPerson ? t.chat.you : t.founder.talk.authors.founder ?? "";
    return (
      <article
        id={compact ? undefined : `message-${message.id}`}
        className={`message ${byPerson ? "from-person" : "from-agent"} is-bubble is-drafted`}
        tabIndex={-1}
        aria-label={t.chat.messageLabel(who, formatDateTime(message.at))}
        data-testid="message-drafting"
        data-author={drafted.author}
      >
        {byPerson ? null : (
          <div className="message-gutter">
            <Avatar name={t.founder.talk.avatarName} kind="agent" size="md" />
          </div>
        )}
        <div className="message-main">
          <header className="message-head">
            <span className="author">{who}</span>
            <RelativeTime at={message.at} className="message-time" />
            <span className="badge drafted-tag">{t.chat.whileDrafting}</span>
          </header>
          <div className="message-content">
            <div className="body">
              <Markdown source={drafted.body} />
            </div>
          </div>
        </div>
      </article>
    );
  }

  if (hasItemNote && detail.item !== undefined) {
    return article(
      "is-note",
      <>
        <ChatItemNote itemId={detail.item} fallback={message.body} time={<RelativeTime at={message.at} className="message-time" />} />
        {hasTools ? toolbar : null}
      </>,
    );
  }

  if (layout === "row") {
    const Icon = systemIcon(detail);
    return article(
      "is-row",
      <>
        <div className="system-row">
          <span className="system-gutter">
            <Icon size={15} aria-hidden="true" className="system-icon" />
          </span>
          <div className="system-text">
            <span className="visually-hidden">{author}: </span>
            <Markdown source={message.body} className="inline" />
          </div>
          <Markers detail={detail} example={isExample} />
          <RelativeTime at={message.at} className="message-time" />
        </div>
        {quote}
        {hasTools ? toolbar : null}
      </>,
    );
  }

  if (layout === "system") {
    const Icon = systemIcon(detail);
    return article(
      hasItemCard ? "is-system is-item" : "is-system",
      <>
        <div className="message-gutter">
          <span className="system-avatar" aria-hidden="true">
            <Icon size={16} />
          </span>
        </div>
        <div className="message-main">
          {/* A decision card says who asks and by when itself; crewmind's name and the time stay in the line's label. */}
          {hasItemCard ? null : (
            <header className="message-head">
              <span className="author">{author}</span>
              <RelativeTime at={message.at} className="message-time" />
              <Markers detail={detail} example={isExample} />
            </header>
          )}
          {quote}
          <div className="message-content">
            {hasActionCard || hasItemCard ? (
              content
            ) : (
              <div className="body">
                <Markdown source={message.body} />
              </div>
            )}
          </div>
          {isStatus ? <StatusActions detail={detail} order={order} request={request} handlers={handlers} /> : null}
          {hasTools ? toolbar : null}
        </div>
      </>,
    );
  }

  const isPerson = kind === "person";
  return article(
    "is-bubble",
    <>
      {isPerson ? null : (
        <div className="message-gutter">
          <AgentAvatar seat={message.author} size="md" />
        </div>
      )}
      <div className="message-main">
        <header className="message-head">
          <span className="author">{mine ? t.chat.you : author}</span>
          {!isPerson && role ? <span className="message-role">{role}</span> : null}
          <RelativeTime at={message.at} className="message-time" />
          <Markers detail={detail} example={isExample} />
          {isPerson && !isStatus ? (
            <span className="tick" data-testid="delivered">
              <CheckCheck size={13} aria-hidden="true" /> {t.chat.delivered}
            </span>
          ) : null}
        </header>
        {quote}
        <div className="message-content">{content}</div>
        {foldable ? (
          <button
            type="button"
            className="button small ghost fold-toggle"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? t.chat.showLess : t.chat.showMore}
          </button>
        ) : null}
        {isStatus ? <StatusActions detail={detail} order={order} request={request} handlers={handlers} /> : null}
        {hasTools ? toolbar : null}
      </div>
    </>,
  );
}

export const MessageItem = memo(MessageItemInner);
