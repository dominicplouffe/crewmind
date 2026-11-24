/** The scrolling chat: stored messages, local notices, messages being sent, and replies being written. */
import { MessageCircle } from "lucide-react";
import { AlertCircle, ArrowDown, CheckCircle2, Loader2, RotateCw, Square, X } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Message } from "../api/client";
import { useAuth } from "../auth";
import { Markdown, Pre } from "../components/common";
import { Empty, Loading } from "../panels/kit";
import { formatValue } from "../lib/format";
import { AgentAvatar, useAgentName } from "../squad/names";
import { t } from "../strings";
import { placements } from "./layout";
import { MessageItem, type MessageHandlers } from "./MessageItem";
import { useMinute } from "./RelativeTime";
import type { ChatState, Notice, PendingMessage, Typing } from "./state";

interface Props {
  state: ChatState;
  handlers: MessageHandlers;
  onRetry(key: string): void;
  onDismissPending(key: string): void;
  onDismissNotice(key: string): void;
  onInterrupt(): void;
  onEarlier(): Promise<void>;
}

const NEAR_BOTTOM_PX = 160;

function NoticeItem({ notice, onDismiss }: { notice: Notice; onDismiss(): void }): JSX.Element {
  const entries = notice.data ? Object.entries(notice.data) : [];
  return (
    <div
      className={`notice ${notice.kind === "error" ? "is-error" : "is-result"}`}
      role={notice.kind === "error" ? "alert" : "status"}
      data-testid={`notice-${notice.kind}`}
    >
      <span className="notice-icon" aria-hidden="true">
        {notice.kind === "error" ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
      </span>
      <div className="notice-main">
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
      </div>
      <button type="button" className="button small ghost icon-only notice-dismiss" onClick={onDismiss} title={t.common.dismiss}>
        <X size={15} aria-hidden="true" />
        <span className="visually-hidden">{t.common.dismiss}</span>
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
    <article
      className={`message from-person is-bubble is-pending ${pending.error ? "has-error" : ""}`}
      aria-label={t.chat.pendingLabel}
    >
      <div className="message-main">
        <div className="message-content">
          <div className="body">
            <Markdown source={pending.body} />
          </div>
        </div>
        {pending.error ? (
          <div className="note note-error" role="alert">
            <p className="note-title">{pending.error.message}</p>
            {pending.error.hint ? <p className="note-hint">{pending.error.hint}</p> : null}
            <div className="note-actions">
              <button type="button" className="button small" onClick={onRetry}>
                <RotateCw size={14} aria-hidden="true" />
                {t.chat.retry}
              </button>
              <button type="button" className="button small ghost" onClick={onDismiss}>
                {t.common.dismiss}
              </button>
            </div>
          </div>
        ) : (
          <span className="quiet pending-state">
            <Loader2 size={13} aria-hidden="true" className="spin" />
            {t.chat.sending}
          </span>
        )}
      </div>
    </article>
  );
}

function TypingItem({ typing, doing, onInterrupt }: { typing: Typing; doing: string | null; onInterrupt(): void }): JSX.Element {
  const { name } = useAgentName()(typing.seat);
  return (
    <article className="message from-agent is-bubble is-typing" aria-label={t.chat.typingLabel(name)} data-testid="typing">
      <div className="message-gutter">
        <AgentAvatar seat={typing.seat} size="md" status="working" />
      </div>
      <div className="message-main">
        <header className="message-head">
          <span className="author">{name}</span>
          <span className="message-role typing-doing">
            <span className="typing-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            {doing ?? t.chat.writing}
          </span>
          <button type="button" className="button small ghost typing-stop" onClick={onInterrupt}>
            <Square size={12} aria-hidden="true" />
            {t.chat.stop}
          </button>
        </header>
        <div className="message-content">
          <div className="body" aria-live="polite" aria-atomic="false">
            <Markdown source={typing.text} />
          </div>
        </div>
      </div>
    </article>
  );
}

export function MessageList({
  state,
  handlers,
  onRetry,
  onDismissPending,
  onDismissNotice,
  onInterrupt,
  onEarlier,
}: Props): JSX.Element {
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  /** The oldest message shown when an earlier page was asked for, and where it sat in the view. */
  const held = useRef<{ id: string; top: number } | null>(null);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  /** Scrolled up, away from the newest message, and how many arrived since. */
  const [away, setAway] = useState(false);
  const [unseen, setUnseen] = useState(0);
  const lastCount = useRef(0);
  const minute = useMinute();
  const { messages, notices, pending, typing, header, cards } = state;
  const myName = useAuth().person?.name;
  const firstId = messages[0]?.id ?? 0;

  // Older messages go in above: put the message the person was reading back where it was. Measuring
  // that message itself, not the distance from the end, stays right when a new message arrives below
  // while the page loads.
  useLayoutEffect(() => {
    const element = scroller.current;
    const was = held.current;
    if (!element || !was) return;
    held.current = null;
    const anchor = document.getElementById(was.id);
    if (anchor) element.scrollTop += topIn(element, anchor) - was.top;
  }, [firstId]);

  const showEarlier = async (): Promise<void> => {
    const element = scroller.current;
    const anchor = document.getElementById(`message-${firstId}`);
    if (element && anchor) {
      held.current = { id: anchor.id, top: topIn(element, anchor) };
      stick.current = false;
    }
    setLoadingEarlier(true);
    await onEarlier();
    setLoadingEarlier(false);
    // The button goes away when the first message is loaded: keep keyboard focus in the list.
    if (!element?.contains(document.activeElement)) element?.focus({ preventScroll: true });
  };

  const byId = useMemo(() => new Map(messages.map((message) => [message.id, message])), [messages]);
  const replyCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const message of messages) {
      if (message.thread_id !== null) counts.set(message.thread_id, (counts.get(message.thread_id) ?? 0) + 1);
    }
    return counts;
  }, [messages]);

  const shown = useMemo(
    () => placements(messages, new Date(minute), { today: t.chat.today, yesterday: t.chat.yesterday }),
    [messages, minute],
  );

  // Messages that arrive while the person reads further up are counted on the "jump" button.
  useEffect(() => {
    const added = messages.length - lastCount.current;
    lastCount.current = messages.length;
    if (added > 0 && !stick.current && state.loaded) setUnseen((count) => count + added);
  }, [messages.length, state.loaded]);

  const toLatest = (): void => {
    const element = scroller.current;
    if (!element) return;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    element.scrollTo({ top: element.scrollHeight, behavior: calm ? "auto" : "smooth" });
    stick.current = true;
    setAway(false);
    setUnseen(0);
  };

  const typingLength = typing.reduce((sum, item) => sum + item.text.length, 0);
  useEffect(() => {
    const element = scroller.current;
    if (element && stick.current) element.scrollTop = element.scrollHeight;
  }, [messages.length, notices.length, pending.length, typingLength, state.loaded]);

  const onScroll = (): void => {
    const element = scroller.current;
    if (!element) return;
    stick.current = element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_BOTTOM_PX;
    setAway(!stick.current);
    if (stick.current) setUnseen(0);
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
      {state.earlier !== null ? (
        <button
          type="button"
          className="button small earlier"
          disabled={loadingEarlier}
          onClick={() => void showEarlier()}
          data-testid="earlier"
        >
          {loadingEarlier ? t.listening.earlierBusy : t.listening.earlier}
        </button>
      ) : null}
      {state.loaded && messages.length === 0 && pending.length === 0 ? (
        <Empty
          icon={MessageCircle}
          title={t.chat.emptyTitle}
          next={header?.state === "draft" ? t.chat.emptyNextDraft : t.chat.emptyNext}
        />
      ) : null}
      {messages.length === 0
        ? notices.map((notice) => <NoticeItem key={notice.key} notice={notice} onDismiss={() => onDismissNotice(notice.key)} />)
        : lead.map((notice) => <NoticeItem key={notice.key} notice={notice} onDismiss={() => onDismissNotice(notice.key)} />)}
      {messages.map((message: Message, index) => (
        <div key={message.id} className={shown[index]?.continued ? "message-slot is-continued" : "message-slot"}>
          {shown[index]?.day ? (
            <div className="day-divider" role="separator" aria-label={shown[index]?.day ?? ""}>
              <span>{shown[index]?.day}</span>
            </div>
          ) : null}
          <MessageItem
            message={message}
            parent={message.reply_to !== null ? byId.get(message.reply_to) : undefined}
            card={cardFor(message, cards)}
            replies={replyCounts.get(message.id) ?? 0}
            handlers={handlers}
            order={subjectOf(message, "order", state.orders)}
            request={subjectOf(message, "request", state.requests)}
            example={state.examples[message.id]}
            mine={message.author_kind === "person" && message.author === myName}
            parentMine={isMine(message.reply_to !== null ? byId.get(message.reply_to) : undefined, myName)}
            continued={shown[index]?.continued ?? false}
            showQuote={shown[index]?.quote ?? true}
          />
          {noticesAfter(message.id, index === messages.length - 1).map((notice) => (
            <NoticeItem key={notice.key} notice={notice} onDismiss={() => onDismissNotice(notice.key)} />
          ))}
        </div>
      ))}
      {pending.filter((item) => !item.echoed || item.error).map((item) => (
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
      {away ? (
        <div className="jump-latest">
          <button type="button" className="button small jump-latest-button" onClick={toLatest} data-testid="jump-latest">
            <ArrowDown size={14} aria-hidden="true" />
            {unseen > 0 ? t.chat.newMessages(unseen) : t.chat.jumpToLatest}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function isMine(message: Message | undefined, myName: string | undefined): boolean {
  return message !== undefined && message.author_kind === "person" && myName !== undefined && message.author === myName;
}

/** How far below the top edge of the scrolling list an element sits now. */
function topIn(scroller: HTMLElement, element: HTMLElement): number {
  return element.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
}

function subjectOf<T>(message: Message, key: "order" | "request", known: Record<number, T>): T | undefined {
  const id = (message.detail as Record<string, unknown> | null)?.[key];
  return typeof id === "number" ? known[id] : undefined;
}

function cardFor(message: Message, cards: ChatState["cards"]): ChatState["cards"][number] | undefined {
  const id = (message.detail as { card?: unknown } | null)?.card;
  return typeof id === "number" ? cards[id] : undefined;
}
