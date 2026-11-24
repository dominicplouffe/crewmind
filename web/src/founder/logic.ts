/**
 * Display helpers for drafting a project with the Founder (FND-3, FND-5, FND-12). No rules live
 * here: whether a draft is ready, what a question recommends and what an answer means are the
 * server's. These only turn a choice on the page into the text the server expects, and lay the
 * server's answers out.
 */
import type { Schemas } from "../api/client";
import { t } from "../strings";

export type Drafting = Schemas["DraftingView"];
export type Line = Schemas["Line"];
export type Question = Schemas["QuestionView"];
export type LedgerLine = Schemas["LedgerLine"];
export type Grade = Schemas["Grade"];
export type ElementGrade = Schemas["ElementGrade"];
export type DraftingItem = Schemas["DraftingItem"];
export type Decision = Schemas["DecisionView"];

/** How many of the decisions are settled, for the progress line. */
export function settledCount(decisions: Decision[]): number {
  return decisions.filter((decision) => decision.state === "settled").length;
}

export type StepName = "describe" | "decide" | "review" | "create";
export const STEPS: StepName[] = ["describe", "decide", "review", "create"];

/** Which step of drafting the person is on: a display of the server's own state, not a rule. */
export function stepOf(view: Drafting, reviewing: boolean): StepName {
  if (view.state === "created" || view.state === "started") return "create";
  if (view.ready) return reviewing ? "review" : "decide";
  return view.draft ? "decide" : "describe";
}

/** The first choice shown for a question: its recommended option, or none when there is none. */
export function firstChoice(question: Question): Choice | null {
  return question.recommended === null ? null : { kind: "option", index: question.recommended };
}

/** The server reads one letter as "that option". A question offers at most four. */
const LETTERS = "abcd";
/** The server reads these as "use the recommendation", so they cannot be sent as a person's own words. */
const MEANS_YES = ["", "y", "yes", "ok", "okay"];

export function letterOf(index: number): string {
  return LETTERS[index] ?? "";
}

export type Choice = { kind: "recommended" } | { kind: "option"; index: number } | { kind: "own"; text: string };

/**
 * The `answer` to send for a choice on a question card, or null when there is nothing to send.
 * Empty text accepts the recommendation, a letter picks an option, anything else is the person's words.
 */
export function answerFor(question: Question, choice: Choice): string | null {
  if (choice.kind === "recommended") return question.recommended === null ? null : "";
  if (choice.kind === "option") {
    return choice.index >= 0 && choice.index < question.options.length ? letterOf(choice.index) || null : null;
  }
  const text = choice.text.trim();
  if (MEANS_YES.includes(text.toLowerCase())) return question.recommended === null ? null : "";
  return text;
}

/** The plain tag for where a ledger line came from. */
export function sourceTag(source: string): string {
  return t.founder.side.source[source] ?? source;
}

/** The plain name of what a ledger line settles: a decision of the tree, or a passage of the document. */
export function decisionName(settles: string): string {
  const known = t.founder.side.decisions[settles];
  if (known) return known;
  const passage = /^item:(\d+)$/.exec(settles);
  if (passage?.[1]) return t.founder.side.passageItem(passage[1]);
  return settles.replace(/_/g, " ");
}

export function elementName(element: string): string {
  return t.founder.side.elements[element] ?? element.replace(/_/g, " ");
}

/** The stored lines to show: a question that is still open is shown as its card, not as a line too. */
export function visibleLines(lines: Line[], open: Question[]): Line[] {
  const waiting = new Set(open.map((question) => question.id));
  return lines.filter((line) => {
    const detail = line.detail as { kind?: unknown; id?: unknown } | null;
    return !(detail?.kind === "question" && typeof detail.id === "number" && waiting.has(detail.id));
  });
}

export type Stage =
  /** Quick mode is running: nothing to answer. */
  | "quick"
  /** It ended failed, with nothing created. */
  | "failed"
  /** A project exists. */
  | "done"
  /** The person may create the project. */
  | "ready"
  /** The Founder owes the next turn. */
  | "founder"
  /** The person owes an answer or a message. */
  | "you";

export function stageOf(view: Drafting): Stage {
  if (view.state === "failed") return "failed";
  if (view.state === "created" || view.state === "started") return "done";
  if (view.quick) return "quick";
  if (view.ready) return "ready";
  return view.waiting_for === "the Founder" ? "founder" : "you";
}

export interface Reason {
  text: string;
  /** The parts of a reason that lists several things. */
  parts: string[];
}

/**
 * The server's reasons a draft is not ready, laid out for reading: a count of open questions in
 * plain words, and a reason that lists several things ("Not yet decided: a; b.") as a list.
 */
export function readinessReasons(reasons: string[]): Reason[] {
  return reasons.map((reason) => {
    const waiting = /^(\d+) question\(s\) are waiting for an answer\.$/.exec(reason);
    if (waiting) {
      const count = Number(waiting[1]);
      return { text: count === 1 ? t.founder.ready.oneQuestion : t.founder.ready.questions(count), parts: [] };
    }
    const listed = /^([^:]{1,40}):\s(.+;.+)$/.exec(reason);
    if (listed?.[1] && listed[2]) {
      const parts = listed[2]
        .replace(/\.$/, "")
        .split(";")
        .map((part) => part.trim())
        .filter(Boolean);
      return { text: `${listed[1]}:`, parts };
    }
    return { text: reason, parts: [] };
  });
}

export const QUICK_STEPS = ["drafting", "creating", "starting", "started"] as const;
export type StepStatus = "done" | "now" | "todo";

/** Where quick mode stands (FND-12): each step done, in progress or not yet. A failure leaves every step as it was. */
export function quickSteps(state: string): { step: string; status: StepStatus }[] {
  const at = QUICK_STEPS.indexOf(state as (typeof QUICK_STEPS)[number]);
  return QUICK_STEPS.map((step, index) => {
    if (at === -1) return { step, status: "todo" as const };
    if (index < at || state === "started") return { step, status: "done" as const };
    return { step, status: index === at ? ("now" as const) : ("todo" as const) };
  });
}

/** The credential names in the server's hint when quick mode asks who pays ("Name one: main, spare."). */
export function credentialsInHint(hint: string | null | undefined): string[] {
  const listed = /:\s*(.+?)\.?\s*$/.exec(hint ?? "");
  if (!listed?.[1]) return [];
  return listed[1]
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
}

export interface DraftTeam {
  name: string;
  role: string;
  members: string[];
}

export interface DraftSummary {
  name: string;
  type: string;
  goal: string;
  quality: string | null;
  budgetTokens: number | null;
  deadline: { date: string; source: string } | null;
  payingCredential: string | null;
  teams: DraftTeam[];
  settings: [name: string, value: unknown][];
}

const text = (value: unknown): string => (typeof value === "string" ? value : "");

/** The parts of a proposed spec the side panel shows. The draft arrives as loose JSON, so every part is checked. */
export function draftSummary(draft: Drafting["draft"]): DraftSummary | null {
  if (!draft) return null;
  const teams = Array.isArray(draft.teams) ? (draft.teams as Record<string, unknown>[]) : [];
  const settings = draft.settings && typeof draft.settings === "object" ? (draft.settings as Record<string, unknown>) : {};
  const deadline = draft.deadline as { date?: unknown; source?: unknown } | null | undefined;
  return {
    name: text(draft.name),
    type: text(draft.type),
    goal: text(draft.goal),
    quality: text(draft.quality) || null,
    budgetTokens: typeof draft.budget_tokens === "number" ? draft.budget_tokens : null,
    deadline: deadline && text(deadline.date) ? { date: text(deadline.date), source: text(deadline.source) } : null,
    payingCredential: text(draft.paying_credential) || null,
    teams: teams
      .filter((team) => team && typeof team === "object")
      .map((team) => ({
        name: text(team.name),
        role: text(team.role),
        members: Array.isArray(team.members) ? team.members.map(text).filter(Boolean) : [],
      })),
    settings: Object.entries(settings),
  };
}

/** The grade as the side panel shows it, or null when there is none yet. */
export function gradeOf(grade: Drafting["grade"]): Grade | null {
  if (!grade || !Array.isArray(grade.elements)) return null;
  return {
    ready: grade.ready === true,
    summary: text(grade.summary),
    missing: Array.isArray(grade.missing) ? grade.missing.map(text) : [],
    weak: Array.isArray(grade.weak) ? grade.weak.map(text) : [],
    elements: (grade.elements as Record<string, unknown>[]).map((element) => ({
      element: text(element.element),
      grade: element.grade === "present" || element.grade === "weak" ? element.grade : "missing",
      quote: text(element.quote),
      reason: text(element.reason),
      fix: text(element.fix),
    })),
  };
}

/** The most text a document may hold; the server refuses more. */
export const DOCUMENT_MOST = 200_000;
const TEXT_FILE = /\.(txt|md|markdown)$/i;

/** Why a chosen file cannot be attached as the document, or null when it can. */
export function documentProblem(name: string, content: string): string | null {
  if (!TEXT_FILE.test(name)) return t.founder.start.notText;
  if (content.trim() === "") return t.founder.start.emptyFile;
  if (content.length > DOCUMENT_MOST) return t.founder.start.tooLong(DOCUMENT_MOST.toLocaleString());
  return null;
}

/** A file name for an exported spec: the project's name in lower case, with anything unsafe taken out. */
export function specFileName(projectName: string): string {
  const safe = projectName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${safe || "project"}.spec.json`;
}

export type CheckKey = "draft" | "passages" | "questions" | "decisions" | "goal" | "rehearsal" | "other";
/** Done, the next thing to do, or not possible until something before it is done. */
export type CheckStatus = "done" | "todo" | "later";

export interface Check {
  key: CheckKey;
  status: CheckStatus;
  /** The server's own reason when this check is not met, shown as given. */
  reason: string | null;
}

/** Which check a reason of the server's `not_ready_because` belongs to (FND-5). */
function checkOfReason(reason: string): CheckKey {
  if (reason === "There is no draft yet.") return "draft";
  if (reason.startsWith("Passages of the document")) return "passages";
  if (/question\(s\) are waiting/.test(reason)) return "questions";
  if (reason.startsWith("Not yet decided")) return "decisions";
  if (/rehears/i.test(reason)) return "rehearsal";
  return "goal";
}

/**
 * What stands between this draft and a project, as a checklist in the order the work happens
 * (FND-5): a draft, the questions answered, every decision made, the goal graded ready, the draft
 * rehearsed. Display only: each check is open exactly when the server gives a reason for it, and the
 * server's `ready` stays the only verdict. Passages of a document show only while some are open.
 */
export function readinessChecks(view: Drafting): Check[] {
  const reasons = new Map<CheckKey, string>();
  for (const reason of view.not_ready_because) {
    const key = checkOfReason(reason);
    reasons.set(key, reasons.has(key) ? `${reasons.get(key) ?? ""} ${reason}` : reason);
  }
  const hasDraft = view.draft !== null && !reasons.has("draft");
  const check = (key: CheckKey, status: CheckStatus): Check => ({ key, status, reason: reasons.get(key) ?? null });
  // Decisions, the goal and the rehearsal are about a draft: before there is one they wait.
  const ofDraft = (key: CheckKey): Check => check(key, !hasDraft ? "later" : reasons.has(key) ? "todo" : "done");
  const checks: Check[] = [check("draft", hasDraft ? "done" : "todo")];
  if (reasons.has("passages")) checks.push(check("passages", "todo"));
  checks.push(
    check("questions", reasons.has("questions") ? "todo" : hasDraft ? "done" : "later"),
    ofDraft("decisions"),
    ofDraft("goal"),
    ofDraft("rehearsal"),
  );
  return checks;
}

/** The one thing this page says is happening now, and what the person can do about it. */
export type Now =
  | { kind: "writing-first" }
  | { kind: "updating" }
  | { kind: "questions"; count: number }
  | { kind: "your-turn" }
  | { kind: "failed-turn" }
  | { kind: "ready" }
  | { kind: "quick" }
  | { kind: "created" }
  | { kind: "ended" };

export function nowOf(view: Drafting): Now {
  const stage = stageOf(view);
  if (stage === "done") return { kind: "created" };
  if (stage === "failed") return { kind: "ended" };
  if (stage === "quick") return { kind: "quick" };
  if (stage === "ready") return { kind: "ready" };
  if (stage === "founder") return view.draft ? { kind: "updating" } : { kind: "writing-first" };
  if (view.questions.length > 0) return { kind: "questions", count: view.questions.length };
  if (view.failure) return { kind: "failed-turn" };
  return { kind: "your-turn" };
}
