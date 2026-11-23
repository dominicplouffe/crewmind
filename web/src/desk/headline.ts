/**
 * The ask of a decision card in plain words (HUM-1, HUM-2): one headline built from the item's kind
 * and typed fields, the subject in the agent's own words, and the size of what is asked. The
 * server's title stays available in the card's details; this only says the same thing shorter.
 * Presentation only: every value comes from the item as the server sent it.
 */
import { t } from "../strings";
import { listField, numberField, textField, type Item } from "./logic";

export interface Headline {
  /** "Add to scope?", "Approve spending $15.00?", "Answer a question". */
  ask: string;
  /** What the ask is about, in the filer's own words: untrusted, shown as plain text (P4). */
  subject: string | null;
  /** The cost or size of what is asked, when there is one: "1 run", "$15.00". */
  size: string | null;
}

type HeadlineInput = Pick<Item, "kind" | "fields" | "recommendation" | "title">;

/** "$15.00", or "15.00 XYZ" when the currency code is not one the browser knows. */
export function money(amount: number, currency: string | null, locale?: string): string {
  const code = currency?.trim().toUpperCase() ?? "";
  if (/^[A-Z]{3}$/.test(code)) {
    try {
      return new Intl.NumberFormat(locale, { style: "currency", currency: code }).format(amount);
    } catch {
      // An unknown code is written out below.
    }
  }
  const plain = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount);
  return code ? `${plain} ${code}` : plain;
}

function whole(value: number | null, locale?: string): string | null {
  return value === null ? null : new Intl.NumberFormat(locale).format(value);
}

/** The headline, subject and size of an item. `locale` is for tests; the page uses the person's own. */
export function headlineOf(item: HeadlineInput, locale?: string): Headline {
  const words = t.decisions.headline;
  const fields = item.fields;
  const text = (name: string): string | null => textField(fields, name);
  const count = (name: string): number | null => numberField(fields, name);
  const own = item.recommendation.trim() || null;
  switch (item.kind) {
    case "proposed scope": {
      const runs = count("estimate_runs");
      return { ask: words["proposed scope"], subject: text("text"), size: runs !== null ? words.size.runs(runs) : null };
    }
    case "proposed commitment":
      return { ask: words["proposed commitment"](text("projected")), subject: null, size: null };
    case "verdict":
      return { ask: words.verdict(count("requirement_id")), subject: text("success_test"), size: null };
    case "reserve draw":
      return { ask: words["reserve draw"](whole(count("tokens"), locale)), subject: text("reason"), size: null };
    case "approval: capacity":
      return { ask: words["approval: capacity"](text("what"), whole(count("amount"), locale)), subject: null, size: null };
    case "approval: spend": {
      const amount = count("amount");
      const price = amount !== null ? money(amount, text("currency"), locale) : null;
      return { ask: words["approval: spend"](price), subject: own, size: null };
    }
    case "approval: legal":
      return { ask: words["approval: legal"], subject: own, size: null };
    case "approval: tool permission":
      return { ask: words["approval: tool permission"](text("tool")), subject: own, size: null };
    case "delivery sign-off": {
      const deliverables = listField(fields, "deliverables").length;
      return { ask: words["delivery sign-off"], subject: null, size: deliverables > 0 ? words.size.deliverables(deliverables) : null };
    }
    case "budget checkpoint": {
      const spent = whole(count("spent"), locale);
      const budget = whole(count("budget"), locale);
      return { ask: words["budget checkpoint"], subject: null, size: spent && budget ? words.size.used(spent, budget) : null };
    }
    case "audit sample":
      return { ask: words["audit sample"](count("task_id")), subject: text("label"), size: null };
    case "reopen request":
      return { ask: words["reopen request"](count("decision_id")), subject: text("reason"), size: null };
    case "question":
      return { ask: words.question, subject: text("question"), size: null };
    case "assist": {
      const what = text("what");
      return { ask: words.assist, subject: text("step"), size: what ? (words.assists[what] ?? what) : null };
    }
    case "heads-up":
      return { ask: words["heads-up"], subject: text("text") ?? own, size: null };
    case "flag":
      return { ask: words.flag(text("flag")), subject: text("cause"), size: null };
    case "mistake report": {
      const cost = whole(count("cost_tokens"), locale);
      return { ask: words["mistake report"], subject: text("because"), size: cost ? words.size.tokens(cost) : null };
    }
    case "status review": {
      const green = typeof fields.green === "boolean" ? fields.green : null;
      return { ask: words["status review"](count("number"), green), subject: text("narrative"), size: null };
    }
    default:
      // A kind this page does not know yet: the server's title, and what it recommends.
      return { ask: item.title, subject: own, size: null };
  }
}

/** Kinds that tell rather than ask: in the chat they are a quiet note, not a card. */
export const NOTE_KINDS: ReadonlySet<string> = new Set(["heads-up", "flag", "mistake report"]);

export function isNote(kind: string | undefined): boolean {
  return kind !== undefined && NOTE_KINDS.has(kind);
}

/** The one quiet line a settled item becomes: "You approved", "Declined by default", "Withdrawn". */
export function settledWords(item: Pick<Item, "state" | "outcome">): string {
  const words = t.decisions.compact;
  const outcome = item.outcome?.trim() ?? "";
  if (item.state === "decided" || item.state === "acknowledged") {
    const verb = words.past[outcome];
    if (verb) return words.settled.you(verb);
    return outcome ? words.settled.otherwise(outcome) : words.settled.state(t.decisions.states[item.state] ?? item.state);
  }
  if (item.state === "defaulted") return words.defaulted[outcome] ?? words.settled.byDefault(outcome);
  return words.settled.state(t.decisions.states[item.state] ?? item.state);
}
