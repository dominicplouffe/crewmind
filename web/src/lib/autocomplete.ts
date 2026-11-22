/** Finds what the person is completing in the composer (a slash command or an @ mention). */

export interface Completion {
  kind: "command" | "mention";
  /** Where the token being completed starts and ends in the text. */
  start: number;
  end: number;
  options: CompletionOption[];
}

export interface CompletionOption {
  /** The text that replaces the token, such as `/hold` or `@CEO`. */
  value: string;
  /** A short line saying what it is. */
  detail: string;
}

export interface MentionTarget {
  name: string;
  detail: string;
}

function startsWithFold(candidate: string, typed: string): boolean {
  return candidate.toLowerCase().startsWith(typed.toLowerCase());
}

/** Slash commands complete only when the message starts with `/` and the cursor is in that word. */
export function commandCompletion(
  text: string,
  cursor: number,
  commands: Record<string, string>,
): Completion | null {
  if (!text.startsWith("/")) return null;
  const end = text.search(/\s/) === -1 ? text.length : text.search(/\s/);
  if (cursor > end) return null;
  const typed = text.slice(0, cursor);
  const options = Object.entries(commands)
    .filter(([name]) => startsWithFold(name, typed))
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, detail]) => ({ value: name, detail }));
  return options.length === 0 ? null : { kind: "command", start: 0, end, options };
}

/** Mentions complete after an `@` that starts the text or follows a space. */
export function mentionCompletion(text: string, cursor: number, targets: MentionTarget[]): Completion | null {
  const before = text.slice(0, cursor);
  const match = /(^|\s)@([^\s@]*)$/.exec(before);
  if (!match) return null;
  const typed = match[2] ?? "";
  const start = cursor - typed.length - 1;
  const rest = text.slice(cursor);
  const tail = /^[^\s@]*/.exec(rest)?.[0] ?? "";
  const options = targets
    .filter((target) => startsWithFold(target.name, typed))
    .map((target) => ({ value: `@${target.name}`, detail: target.detail }));
  return options.length === 0 ? null : { kind: "mention", start, end: cursor + tail.length, options };
}

export function findCompletion(
  text: string,
  cursor: number,
  commands: Record<string, string>,
  targets: MentionTarget[],
): Completion | null {
  return commandCompletion(text, cursor, commands) ?? mentionCompletion(text, cursor, targets);
}

/** Replaces the token being completed and returns the new text and cursor position. */
export function applyCompletion(
  text: string,
  completion: Completion,
  option: CompletionOption,
): { text: string; cursor: number } {
  const after = text.slice(completion.end);
  const spacer = after.startsWith(" ") ? "" : " ";
  const head = text.slice(0, completion.start) + option.value + spacer;
  return { text: head + after, cursor: head.length + (spacer ? 0 : 1) };
}

export function isCommand(text: string): boolean {
  return text.trimStart().startsWith("/");
}
