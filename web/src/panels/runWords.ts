/**
 * A run in plain words (P18): "CEO worked on a directive · finished 4 min ago". Presentation only:
 * the kind, state and reasons are the server's; unknown ones are shown as given.
 */
import { fromNow } from "../lib/humanize";
import { t } from "../strings";

const PERSON_MESSAGE = /^message \d+ from a person$/;
const NOTICE = /^notice: (.+)$/;

/** One reason a run started, as the object of the sentence. */
export function reasonWords(reason: string): string {
  const words = t.runs;
  if (PERSON_MESSAGE.test(reason)) return words.reasons["your message"] ?? reason;
  const notice = NOTICE.exec(reason);
  if (notice) {
    const kind = notice[1] ?? "";
    return words.notices[kind] ?? kind;
  }
  return words.reasons[reason] ?? reason;
}

/** The reasons, without repeats, joined with "and". */
export function aboutWords(reasons: readonly string[]): string {
  const unique = [...new Set(reasons.map(reasonWords))];
  if (unique.length <= 1) return unique[0] ?? "";
  return `${unique.slice(0, -1).join(", ")}${t.runs.and}${unique[unique.length - 1]}`;
}

export interface RunLike {
  seat: string;
  kind: string;
  state: string;
  reasons: string[];
  queued_at: string;
  started_at?: string | null;
  ended_at?: string | null;
}

/** "Maya worked on a directive". `name` is the name the agent goes by (EXE-18); the seat name otherwise. */
export function runSentence(run: Pick<RunLike, "seat" | "kind" | "reasons">, name?: string): string {
  const about = aboutWords(run.reasons);
  const doing = t.runs.doing[run.kind];
  return t.runs.sentence(name ?? run.seat, doing ? doing(about) : t.runs.doingOther(run.kind, about));
}

/** "finished 4 minutes ago", "working now", "waiting to start". */
export function runStateWords(run: RunLike, now: number = Date.now()): string {
  const at = run.ended_at ?? run.started_at ?? run.queued_at;
  const ago = fromNow(at, now);
  const word = t.runs.states[run.state];
  return word ? word(ago) : t.runs.stateOther(run.state, ago);
}

/** The tone of a run's state, for its dot: the word beside it carries the meaning. */
export function runTone(state: string): "success" | "accent" | "danger" | "warning" | "neutral" {
  if (state === "finished") return "success";
  if (state === "running" || state === "leased") return "accent";
  if (state === "failed" || state === "reaped") return "danger";
  if (state === "killed" || state === "terminated") return "warning";
  return "neutral";
}
