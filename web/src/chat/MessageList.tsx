/** The scrolling chat: stored messages, local notices, messages being sent, and replies being written. */
import { useEffect, useMemo, useRef } from "react";
import type { Message } from "../api/client";
import { Empty, Loading, Markdown, Pre } from "../components/common";
import { formatValue } from "../lib/format";
import { t } from "../strings";
import { MessageItem, type MessageHandlers } from "./MessageItem";
import type { ChatState, Notice, PendingMessage, Typing } from "./state";

interface Props {
  state: ChatState;
  handlers: MessageHandlers;
  onRetry(key: string): void;
  onDismissPending(key: string): void;
  onDismissNotice(key: string): void;
  onInterrupt(): void;
}

const NEAR_BOTTOM_PX = 160;

function NoticeItem({ notice, onDismiss }: { notice: Notice; onDismiss(): void }): JSX.Element {
  const entries = notice.data ? Object.entries(notice.data) : [];
  return (
    <div
      className={`notice ${notice.kind === "error" ? "note-error" : ""}`}
      role={notice.kind === "error" ? "alert" : "status"}
      data-testid={`notice-${notice.kind}`}
    >
      <p className="note-title">{notice.kind === "error" ? notice.text : notice.title}</p>
      {notice.hint ? <p className="note-hint">{notice.hint}</p> : null}
      {entries.length > 0 ? (
        <dl className="pairs">
          {entries.map(([key, value]) => (
            <div key={key}>
              <dt>{key.replace(/_/g, " ")}</dt>
              <dd>{typeof value === "object" && value !== null ? <Pre>{formatValue(value)}</Pre> : formatValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <button type="button" className="link" onClick={onDismiss}>
        {t.common.dismiss}
      </button>
    </div>
  );
}

function PendingItem({
  pending,
  onRetry,
  onDismiss,
}: {
  pending: PendingMessage;
  onRetry(): void;
  onDismiss(): void;
}): JSX.Element {
  return (
    <article className="message from-person is-pending" aria-label={t.chat.pendingLabel}>
      <div className="body">
        <Markdown source={pending.body} />
      </div>
      {pending.error ? (
        <div className="note note-error" role="alert">
          <p className="note-title">{pending.error.message}</p>
          {pending.error.hint ? <p className="note-hint">{pending.error.hint}</p> : null}
          <div className="row">
            <button type="button" className="button small" onClick={onRetry}>
              {t.chat.retry}
            </button>
            <button type="button" className="button small" onClick={onDismiss}>
              {t.common.dismiss}
            </button>
          </div>
        </div>
      ) : (
        <span className="quiet">{t.chat.sending}</span>
      )}
    </article>
  );
}

function TypingItem({ typing, doing, onInterrupt }: { typing: Typing; doing: string | null; onInterrupt(): void }): JSX.Element {
  return (
    <article className="message from-agent is-typing" aria-label={t.chat.typingLabel(typing.seat)} data-testid="typing">
      <header className="message-head">
        <span className="author">{typing.seat}</span>
        <span className="quiet">{doing ?? t.chat.writing}</span>
        <button type="button" className="link" onClick={onInterrupt}>
          {t.chat.stop}
        </button>
      </header>
      <div className="body" aria-live="polite" aria-atomic="false">
        <Markdown source={typing.text} />
      </div>
    </article>
  );
}

export function MessageList({ state, handlers, onRetry, onDismissPending, onDismissNotice, onInterrupt }: Props): JSX.Element {
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const { messages, notices, pending, typing, header, cards } = state;

  const byId = useMemo(() => new Map(messages.map((message) => [message.id, message])), [messages]);
  const replyCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const message of messages) {
      if (message.thread_id !== null) counts.set(message.thread_id, (counts.get(message.thread_id) ?? 0) + 1);
    }
    return counts;
  }, [messages]);

  const typingLength = typing.reduce((sum, item) => sum + item.text.length, 0);
  useEffect(() => {
    const element = scroller.current;
    if (element && stick.current) element.scrollTop = element.scrollHeight;
  }, [messages.length, notices.length, pending.length, typingLength, state.loaded]);

  const onScroll = (): void => {
    const element = scroller.current;
    if (!element) return;
    stick.current = element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_BOTTOM_PX;
  };

  const noticesAfter = (id: number, last: boolean): Notice[] =>
    notices.filter((notice) => notice.afterMessage === id || (last && notice.afterMessage > id));
  const lead = notices.filter((notice) => notice.afterMessage === 0 && messages.length > 0);
  const doingFor = (seat: string): string | null => header?.now.find((work) => work.seat === seat)?.doing ?? null;

  return (
    // The log is focusable so keyboard users can scroll it.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className="messages" ref={scroller} onScroll={onScroll} tabIndex={0} role="log" aria-live="polite" aria-label={t.chat.logLabel}>
      {!state.loaded ? <Loading label={t.chat.loading} /> : null}
      {state.loaded && messages.length === 0 && pending.length === 0 ? (
        <Empty
          title={t.chat.emptyTitle}
          next={header?.state === "draft" ? t.chat.emptyNextDraft : t.chat.emptyNext}
        />
      ) : null}
      {messages.length === 0
        ? notices.map((notice) => (
            <NoticeItem key={notice.key} notice={notice} onDismiss={() => onDismissNotice(notice.key)} />
          ))
        : lead.map((notice) => (
            <NoticeItem key={notice.key} notice={notice} onDismiss={() => onDismissNotice(notice.key)} />
          ))}
      {messages.map((message: Message, index) => (
        <div key={message.id} className="message-slot">
          <MessageItem
            message={message}
            parent={message.reply_to !== null ? byId.get(message.reply_to) : undefined}
            card={cardFor(message, cards)}
            replies={replyCounts.get(message.id) ?? 0}
            handlers={handlers}
          />
          {noticesAfter(message.id, index === messages.length - 1).map((notice) => (
            <NoticeItem key={notice.key} notice={notice} onDismiss={() => onDismissNotice(notice.key)} />
          ))}
        </div>
      ))}
      {pending.map((item) => (
        <PendingItem
          key={item.key}
          pending={item}
          onRetry={() => onRetry(item.key)}
          onDismiss={() => onDismissPending(item.key)}
        />
      ))}
      {typing.map((item) => (
        <TypingItem key={item.runId} typing={item} doing={doingFor(item.seat)} onInterrupt={onInterrupt} />
      ))}
    </div>
  );
}

function cardFor(message: Message, cards: ChatState["cards"]): ChatState["cards"][number] | undefined {
  const id = (message.detail as { card?: unknown } | null)?.card;
  return typeof id === "number" ? cards[id] : undefined;
}
