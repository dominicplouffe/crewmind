/**
 * How the chat lays out its messages (CHAT-10, CHAT-11, P18): a divider where the day changes,
 * messages from the same speaker in a row shown as one group, and the quote of the message a reply
 * answers only where that message is not the one just above it. Display only: every reply stays
 * threaded to the message it answers, and the quote is always one click from it.
 */
import type { Message } from "../api/client";
import { draftingLine } from "./MessageExtras";

export interface Placement {
  /** The day to name above this message, when it is the first of its day. */
  day: string | null;
  /** The message goes on the group of the one above: same speaker, nothing between. */
  continued: boolean;
  /** Show the quote of the message this one replies to. */
  quote: boolean;
}

/**
 * Who speaks in a message, for grouping, or null when the message stands alone: nightsquad's own
 * lines and cards never join a group, and neither does anything after them.
 */
export function speakerOf(message: Message): string | null {
  const drafted = draftingLine(message);
  if (drafted) return `drafting:${drafted.author}`;
  if (message.kind === "status" || message.author_kind === "platform") return null;
  const detail = message.detail as { kind?: unknown } | null;
  if (detail?.kind === "action card") return null;
  return `${message.author_kind}:${message.author}`;
}

/** The calendar day of a time, in the viewer's time zone, as a key. */
export function dayKey(iso: string): string {
  const date = new Date(iso);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

/** "Today", "Yesterday", or the date, for the divider above the first message of a day. */
export function dayLabel(iso: string, now: Date, words: { today: string; yesterday: string }): string {
  const date = new Date(iso);
  if (dayKey(iso) === dayKey(now.toISOString())) return words.today;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (dayKey(iso) === dayKey(yesterday.toISOString())) return words.yesterday;
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

export function placements(
  messages: Message[],
  now: Date,
  words: { today: string; yesterday: string },
): Placement[] {
  return messages.map((message, index) => {
    const before = index > 0 ? messages[index - 1] : undefined;
    const newDay = before === undefined || dayKey(before.at) !== dayKey(message.at);
    const speaker = speakerOf(message);
    const answersAbove = message.reply_to !== null && before !== undefined && message.reply_to === before.id;
    const continued =
      !newDay &&
      speaker !== null &&
      before !== undefined &&
      speakerOf(before) === speaker &&
      (message.reply_to === null || answersAbove);
    return {
      day: newDay ? dayLabel(message.at, now, words) : null,
      continued,
      quote: message.reply_to !== null && !answersAbove,
    };
  });
}
