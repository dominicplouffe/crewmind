/**
 * How each governed setting (Appendix A) is shown to a person: its group, the kind of control, the
 * unit it is shown in, and how a typed value turns back into the value the server stores.
 *
 * Presentation only. The server validates every change (GOV-1); the range shown here is read from
 * the registry's own `allowed` and `unit` strings, defensively, so a setting the web app does not
 * know yet still gets a humanised label and a plain control.
 */
import { groupWords, settingWords, settingsWords, unitWords, type SettingWords } from "../strings.settings";

export type GroupId = keyof typeof groupWords;

export type Kind =
  | "choice"
  | "toggle"
  | "number"
  | "duration"
  | "percent"
  | "tokens"
  | "bytes"
  | "money"
  | "time"
  | "timezone"
  | "currency"
  | "url"
  | "text";

export type StoredValue = string | number | boolean;

interface Spec {
  group: GroupId;
  kind: Kind;
  /** A stored word that stands for off, forever and the like (it has a checkbox of its own). */
  special?: string;
}

/** The order groups are shown in. */
export const GROUP_ORDER: GroupId[] = [
  "quality",
  "budget",
  "runs",
  "planning",
  "decisions",
  "conversation",
  "notifications",
  "memory",
  "integrations",
  "files",
  "privacy",
  "region",
  "founder",
  "other",
];

const SPECS: Record<string, Spec> = {
  quality: { group: "quality", kind: "choice" },
  "budget.tokens": { group: "budget", kind: "tokens" },
  "budget.ceo_reserve": { group: "budget", kind: "percent" },
  "budget.warn_at": { group: "budget", kind: "percent" },
  "budget.wrapup_at": { group: "budget", kind: "percent" },
  "budget.reserve_min_done": { group: "budget", kind: "percent" },
  "run.max_tokens": { group: "budget", kind: "tokens" },
  "spend.enabled": { group: "budget", kind: "toggle" },
  "spend.currency": { group: "budget", kind: "currency" },
  "spend.monthly_cap": { group: "budget", kind: "money" },
  "spend.approval_at": { group: "budget", kind: "money" },
  "run.timeout": { group: "runs", kind: "duration" },
  "run.concurrency": { group: "runs", kind: "number" },
  "agent.max_wakes_per_hour": { group: "runs", kind: "number" },
  "spin.window": { group: "runs", kind: "number" },
  "refusal.cap": { group: "runs", kind: "number" },
  "heartbeat.every": { group: "runs", kind: "duration" },
  "stall.after": { group: "runs", kind: "duration" },
  "start.first_task_within": { group: "runs", kind: "duration" },
  "output.first_within": { group: "runs", kind: "duration" },
  "seat.idle_after": { group: "runs", kind: "duration" },
  "rehearsal.max_seconds": { group: "runs", kind: "duration" },
  "review.independent": { group: "quality", kind: "toggle" },
  "audit.sample_rate": { group: "quality", kind: "percent" },
  "audit.window": { group: "quality", kind: "duration" },
  "evidence.min_share": { group: "quality", kind: "percent" },
  "evidence.drought_after": { group: "quality", kind: "duration" },
  "tasks.max_open": { group: "planning", kind: "number" },
  "tasks.max_subtasks": { group: "planning", kind: "number" },
  "teams.max": { group: "planning", kind: "number" },
  "explore.timebox": { group: "planning", kind: "duration" },
  "bet.window": { group: "planning", kind: "duration" },
  "metric.read_every": { group: "planning", kind: "duration" },
  "review.every": { group: "planning", kind: "duration" },
  "watch.min_interval": { group: "planning", kind: "duration" },
  "cycle.period": { group: "planning", kind: "choice" },
  "cycle.roll_day": { group: "planning", kind: "number" },
  "cycle.due_time": { group: "planning", kind: "duration", special: "cycle_end" },
  "authority.preset": { group: "decisions", kind: "choice" },
  "authority.accept_scope": { group: "decisions", kind: "choice" },
  "authority.change_scope": { group: "decisions", kind: "choice" },
  "authority.date": { group: "decisions", kind: "choice" },
  "authority.verdict": { group: "decisions", kind: "choice" },
  "authority.credential_rescope": { group: "decisions", kind: "choice" },
  "authority.reserve_draw": { group: "decisions", kind: "choice" },
  "approval.window": { group: "decisions", kind: "duration" },
  "question.window": { group: "decisions", kind: "duration" },
  "question.max_open": { group: "decisions", kind: "number" },
  "decision.reopen_cooldown": { group: "decisions", kind: "duration" },
  "completion.auto_after": { group: "decisions", kind: "duration" },
  "reopen.window": { group: "decisions", kind: "duration" },
  "chat.brevity": { group: "conversation", kind: "choice" },
  "agent.message_words": { group: "conversation", kind: "number" },
  "thread.freeze_after": { group: "conversation", kind: "number" },
  "correction.ttl": { group: "conversation", kind: "duration", special: "forever" },
  "listening.flag_at": { group: "conversation", kind: "number" },
  "report.cadence": { group: "conversation", kind: "number", special: "off" },
  "chat.keep_warm": { group: "conversation", kind: "duration" },
  "grill.pace": { group: "conversation", kind: "choice" },
  "grill.min_characters": { group: "conversation", kind: "number" },
  "memory.pinned_project_tokens": { group: "memory", kind: "tokens" },
  "memory.pinned_agent_tokens": { group: "memory", kind: "tokens" },
  "memory.recall_k": { group: "memory", kind: "number" },
  "memory.chat_extract_every": { group: "memory", kind: "number" },
  "alerts.level": { group: "notifications", kind: "choice" },
  "alerts.grace": { group: "notifications", kind: "duration" },
  "alerts.max_per_day": { group: "notifications", kind: "number" },
  "brief.time": { group: "notifications", kind: "time", special: "off" },
  "brief.away_after": { group: "notifications", kind: "duration" },
  "agenda.days": { group: "notifications", kind: "number" },
  "email.mode": { group: "integrations", kind: "choice" },
  "email.max_per_day": { group: "integrations", kind: "number" },
  "email.max_new_threads_per_day": { group: "integrations", kind: "number" },
  "email.thread_freeze_after": { group: "integrations", kind: "number" },
  "email.agent_addresses": { group: "integrations", kind: "toggle" },
  "search.max_per_day": { group: "integrations", kind: "number" },
  "browser.keep_sessions": { group: "integrations", kind: "toggle" },
  "a2a.enabled": { group: "integrations", kind: "toggle" },
  "upload.max_size": { group: "files", kind: "bytes" },
  "artifact.max_size": { group: "files", kind: "bytes" },
  "storage.quota": { group: "files", kind: "bytes" },
  "delete.grace": { group: "files", kind: "duration" },
  "retention.traces": { group: "files", kind: "duration", special: "forever" },
  "retention.snapshots": { group: "files", kind: "duration", special: "forever" },
  "otel.endpoint": { group: "privacy", kind: "url", special: "none" },
  "otel.capture_content": { group: "privacy", kind: "toggle" },
  "token.default_expiry": { group: "privacy", kind: "duration" },
  "project.timezone": { group: "region", kind: "timezone" },
  "person.timezone": { group: "region", kind: "timezone" },
  "founder.credential": { group: "founder", kind: "text", special: "none" },
  "founder.model_class": { group: "founder", kind: "choice" },
};

/** Every setting this file describes (the test checks it against Appendix A). */
export const DESCRIBED_SETTINGS: readonly string[] = Object.keys(SPECS);

export interface Choice {
  value: string;
  label: string;
}

export interface SettingMeta {
  name: string;
  group: GroupId;
  kind: Kind;
  label: string;
  help: string;
  choices: Choice[];
  noun: [string, string] | null;
  special: { value: string; toggle: string; summary: string } | null;
  /** False when the web app has no description and fell back to a humanised name. */
  described: boolean;
}

/** "run.max_tokens" → "Run max tokens". Never shown as the raw key. */
export function humanizeName(name: string): string {
  const words = name
    .replace(/[._-]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : name;
}

function guessKind(unit: string | null | undefined, value: unknown): Kind {
  switch ((unit ?? "").toLowerCase()) {
    case "seconds":
    case "minutes":
    case "hours":
    case "days":
      return "duration";
    case "bytes":
      return "bytes";
    case "tokens":
      return "tokens";
    case "percent":
      return "percent";
  }
  if (typeof value === "boolean") return "toggle";
  if (typeof value === "number") return "number";
  return "text";
}

/** What the web app knows about one setting, or a plain fallback for one it doesn't. */
export function metaOf(name: string, unit?: string | null, value?: unknown): SettingMeta {
  const spec = SPECS[name];
  const words: SettingWords | undefined = settingWords[name];
  const kind = spec?.kind ?? guessKind(unit, value);
  const choices = Object.entries(words?.options ?? {}).map(([choice, label]) => ({ value: choice, label }));
  return {
    name,
    group: spec?.group ?? "other",
    kind: kind === "choice" && choices.length === 0 ? "text" : kind,
    label: words?.label ?? humanizeName(name),
    help: words?.help ?? "",
    choices,
    noun: words?.noun ?? null,
    special: spec?.special && words?.special ? { value: spec.special, ...words.special } : null,
    described: Boolean(spec && words),
  };
}

// ---------- Units ----------

export type DurationUnit = "seconds" | "minutes" | "hours" | "days";
export const DURATION_UNITS: { unit: DurationUnit; seconds: number }[] = [
  { unit: "seconds", seconds: 1 },
  { unit: "minutes", seconds: 60 },
  { unit: "hours", seconds: 3600 },
  { unit: "days", seconds: 86400 },
];
const SECONDS_IN: Record<DurationUnit, number> = { seconds: 1, minutes: 60, hours: 3600, days: 86400 };

export type ByteUnit = "MB" | "GB";
const BYTES_IN: Record<ByteUnit, number> = { MB: 1024 ** 2, GB: 1024 ** 3 };

/** Multipliers for the quantities written in `allowed` strings, into the server's base units. */
const QUANTITY_UNITS: Record<string, number> = {
  s: 1,
  sec: 1,
  second: 1,
  seconds: 1,
  min: 60,
  minute: 60,
  minutes: 60,
  h: 3600,
  hour: 3600,
  hours: 3600,
  day: 86400,
  days: 86400,
  week: 604800,
  weeks: 604800,
  k: 1e3,
  m: 1e6,
  b: 1e9,
  kb: 1024,
  mb: 1024 ** 2,
  gb: 1024 ** 3,
  tb: 1024 ** 4,
  "%": 1,
};

/** The server's stored unit, in its base unit (seconds for time, bytes for size). */
function storedScale(unit: string | null | undefined): number {
  switch ((unit ?? "").toLowerCase()) {
    case "minutes":
      return 60;
    case "hours":
      return 3600;
    case "days":
      return 86400;
    default:
      return 1;
  }
}

export interface Range {
  /** In the stored unit. */
  min?: number;
  max?: number;
  /** 0 is allowed and means off, even below `min`. */
  offAtZero: boolean;
}

const QUANTITY = String.raw`(\d[\d,]*(?:\.\d+)?)\s*([a-zA-Z%]+)?`;
const RANGE = new RegExp(String.raw`^${QUANTITY}\s*[–—-]\s*(?:${QUANTITY}|(forever))(?:\s+[a-zA-Z ]+)?$`);
const AT_LEAST = new RegExp(String.raw`^${QUANTITY}\s+or more$`);

function quantity(amount: string | undefined, unit: string | undefined, inherited?: string): number | undefined {
  if (amount === undefined) return undefined;
  const value = Number(amount.replace(/,/g, ""));
  if (!Number.isFinite(value)) return undefined;
  const word = (unit ?? inherited ?? "").toLowerCase();
  // Case matters for one letter: "M" is a million tokens; "m" never appears for minutes.
  const scale = QUANTITY_UNITS[word] ?? 1;
  return value * scale;
}

/**
 * Reads the registry's `allowed` text ("10–360 min", "0 (off) or 100k–50M", "1 MB–2 GB",
 * "1 day–forever", "1M or more") into a range in the stored unit. Anything it can't read gives
 * an empty range: the server still checks every value.
 */
export function parseAllowed(allowed: string | null | undefined, unit?: string | null): Range {
  let text = (allowed ?? "").trim();
  const offAtZero = /\(off\)/i.test(text);
  if (/\bor\b/.test(text) && !/\bor more$/.test(text)) text = text.split(/\bor\b/).pop() ?? "";
  text = text.replace(/\([^)]*\)/g, " ").replace(/\s+/g, " ").trim();
  const scale = storedScale(unit);
  const scaled = (value: number | undefined): number | undefined =>
    value === undefined ? undefined : Math.round((value / scale) * 1e6) / 1e6;

  const atLeast = AT_LEAST.exec(text);
  if (atLeast) return { min: scaled(quantity(atLeast[1], atLeast[2])), offAtZero };
  const range = RANGE.exec(text);
  if (!range) return { offAtZero };
  const [, lowAmount, lowUnit, highAmount, highUnit] = range;
  const high = highAmount === undefined ? undefined : quantity(highAmount, highUnit);
  const low = quantity(lowAmount, lowUnit, highUnit);
  if (low === undefined || (high !== undefined && high < low)) return { offAtZero };
  return { min: scaled(low), max: scaled(high), offAtZero };
}

// ---------- Formatting ----------

const decimal = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 });

function counted(value: number, words: readonly [string, string]): string {
  return `${decimal.format(value)} ${value === 1 ? words[0] : words[1]}`;
}

/** The largest unit in which `seconds` is a whole number: 5400 → minutes, 21600 → hours. */
export function bestDurationUnit(seconds: number): DurationUnit {
  for (const { unit, seconds: size } of [...DURATION_UNITS].reverse()) {
    if (seconds >= size && seconds % size === 0) return unit;
  }
  return seconds >= 60 && seconds % 60 === 0 ? "minutes" : "seconds";
}

/** 5400 → "90 minutes", 21600 → "6 hours", 0 → "0 minutes". */
export function formatDuration(seconds: number): string {
  if (seconds === 0) return counted(0, unitWords.minutes);
  const unit = bestDurationUnit(seconds);
  return counted(seconds / SECONDS_IN[unit], unitWords[unit]);
}

/** The units a duration can be typed in, from the range: run.timeout (10 min to 6 h) → minutes, hours. */
export function durationUnitsFor(range: Range, seconds?: number): DurationUnit[] {
  const order = DURATION_UNITS.map((entry) => entry.unit);
  const lowest = range.min && range.min > 0 ? bestDurationUnit(range.min) : "minutes";
  const fitting = DURATION_UNITS.filter((entry) => range.max === undefined || entry.seconds <= range.max);
  const highest = range.max === undefined ? "days" : (fitting[fitting.length - 1]?.unit ?? lowest);
  let from = order.indexOf(lowest);
  let to = Math.max(from, order.indexOf(highest));
  if (seconds !== undefined && seconds > 0) {
    const current = order.indexOf(bestDurationUnit(seconds));
    from = Math.min(from, current);
    to = Math.max(to, current);
  }
  return order.slice(from, to + 1);
}

export function bestByteUnit(bytes: number): ByteUnit {
  return bytes >= BYTES_IN.GB && bytes % BYTES_IN.GB === 0 ? "GB" : "MB";
}

export function formatBytes(bytes: number): string {
  const unit = bytes >= BYTES_IN.GB ? "GB" : "MB";
  return `${decimal.format(bytes / BYTES_IN[unit])} ${unit}`;
}

/** 3000000 → "3M", 6000 → "6K", 950 → "950". */
export function formatTokenAmount(value: number): string {
  return Math.abs(value) < 1000 ? decimal.format(value) : compact.format(value);
}

export function formatTokens(value: number): string {
  return `${formatTokenAmount(value)} ${value === 1 ? unitWords.tokens[0] : unitWords.tokens[1]}`;
}

/** "3M", "500k", "1.5m", "3,000,000", "3000000 tokens" → a number of tokens. */
export function parseTokens(text: string): number | null {
  const match = /^\s*(\d[\d,]*(?:\.\d+)?)\s*([kmb])?\s*(?:tokens?)?\s*$/i.exec(text);
  if (!match?.[1]) return null;
  const value = Number(match[1].replace(/,/g, ""));
  if (!Number.isFinite(value)) return null;
  const scale = { k: 1e3, m: 1e6, b: 1e9 }[(match[2] ?? "").toLowerCase() as "k" | "m" | "b"] ?? 1;
  return Math.round(value * scale);
}

function formatMoney(value: number, currency?: string): string {
  if (currency && /^[A-Z]{3}$/.test(currency)) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
    } catch {
      // Fall through to a plain number.
    }
  }
  return currency ? `${decimal.format(value)} ${currency}` : decimal.format(value);
}

export interface FormatContext {
  currency?: string;
}

/** One value as a person reads it: "90 minutes", "3M tokens", "80%", "Balanced", "Off". */
export function formatSetting(meta: SettingMeta, value: unknown, range?: Range, context: FormatContext = {}): string {
  const words = settingsWords.control;
  if (meta.special && value === meta.special.value) return meta.special.summary;
  if (typeof value === "boolean") return value ? words.on : words.off;
  if (typeof value === "number") {
    if (value === 0 && range?.offAtZero) return meta.kind === "tokens" ? words.noLimit : words.off;
    switch (meta.kind) {
      case "duration":
        return formatDuration(value);
      case "tokens":
        return formatTokens(value);
      case "bytes":
        return formatBytes(value);
      case "percent":
        return `${decimal.format(value)}%`;
      case "money":
        return formatMoney(value, context.currency);
      default:
        return meta.noun ? counted(value, meta.noun) : decimal.format(value);
    }
  }
  if (typeof value === "string") {
    const choice = meta.choices.find((option) => option.value === value);
    if (choice) return choice.label;
    return value;
  }
  return value === null || value === undefined ? "" : JSON.stringify(value);
}

/** The allowed range in words, in display units: "10 minutes to 6 hours", "1M tokens or more". */
export function rangeText(meta: SettingMeta, range: Range, context: FormatContext = {}): string {
  const words = settingsWords.control;
  const show = (value: number): string => formatSetting({ ...meta, special: null }, value, { offAtZero: false }, context);
  let text = "";
  if (range.min !== undefined && range.max !== undefined) text = words.between(show(range.min), show(range.max));
  else if (range.min !== undefined) text = words.atLeast(show(range.min));
  else if (range.max !== undefined) text = words.atMost(show(range.max));
  return text;
}

// ---------- Editing ----------

/** What a control holds while a person types: the text, the chosen unit, and the special checkbox. */
export interface EditState {
  text: string;
  unit: string;
  special: boolean;
}

export type Parsed = { ok: true; value: StoredValue } | { ok: false; error: string };

function plainNumber(value: number): string {
  return String(Number(value.toFixed(4)));
}

/** The edit state for a stored value: 5400 seconds → { text: "90", unit: "minutes" }. */
export function editStateOf(meta: SettingMeta, range: Range, value: unknown): EditState {
  const special = Boolean(meta.special && value === meta.special.value);
  const number = typeof value === "number" ? value : undefined;
  switch (meta.kind) {
    case "toggle":
      return { text: value === true ? "on" : "off", unit: "", special };
    case "duration": {
      const fallback = range.min ?? 3600;
      const seconds = number ?? fallback;
      const units = durationUnitsFor(range, seconds);
      const best = bestDurationUnit(seconds);
      const unit: DurationUnit = units.includes(best)
        ? best
        : (units.find((entry) => seconds % SECONDS_IN[entry] === 0) ?? units[0] ?? "minutes");
      return { text: number === undefined ? "" : plainNumber(seconds / SECONDS_IN[unit]), unit, special };
    }
    case "bytes": {
      const unit = number === undefined ? "MB" : bestByteUnit(number);
      return { text: number === undefined ? "" : plainNumber(number / BYTES_IN[unit]), unit, special };
    }
    case "tokens":
      return { text: number === undefined ? "" : formatTokenAmount(number).replace(/\s/g, ""), unit: "", special };
    default:
      if (number !== undefined) return { text: plainNumber(number), unit: "", special };
      return { text: special || value === null || value === undefined ? "" : String(value), unit: "", special };
  }
}

const WHOLE_KINDS: Kind[] = ["number", "duration", "percent", "tokens", "bytes"];

function checkRange(meta: SettingMeta, range: Range, value: number, context: FormatContext): Parsed {
  const words = settingsWords.control;
  if (!Number.isFinite(value)) return { ok: false, error: words.needNumber };
  if (value === 0 && range.offAtZero) return { ok: true, value: 0 };
  const tooLow = range.min !== undefined && value < range.min;
  const tooHigh = range.max !== undefined && value > range.max;
  if (tooLow || tooHigh) {
    const show = (bound: number): string => formatSetting({ ...meta, special: null }, bound, { offAtZero: false }, context);
    let error: string;
    if (range.min !== undefined && range.max !== undefined) error = words.outOfRange(rangeText(meta, range, context));
    else if (tooLow) error = words.tooLow(show(range.min as number));
    else error = words.tooHigh(show(range.max as number));
    return { ok: false, error: range.offAtZero ? `${error} ${words.offAtZero}` : error };
  }
  return { ok: true, value };
}

function numberFrom(text: string): number | null {
  const trimmed = text.trim().replace(/,/g, "");
  if (trimmed === "" || !/^-?\d*\.?\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

/** Turns what was typed back into the stored value, or says what's wrong in display units. */
export function valueOf(meta: SettingMeta, range: Range, state: EditState, context: FormatContext = {}): Parsed {
  const words = settingsWords.control;
  if (meta.special && state.special) return { ok: true, value: meta.special.value };
  const text = state.text.trim();
  switch (meta.kind) {
    case "toggle":
      return { ok: true, value: state.text === "on" };
    case "choice":
      return text ? { ok: true, value: text } : { ok: false, error: words.needText };
    case "tokens": {
      const tokens = parseTokens(text);
      return tokens === null ? { ok: false, error: words.needNumber } : checkRange(meta, range, tokens, context);
    }
    case "duration":
    case "bytes":
    case "percent":
    case "number":
    case "money": {
      const amount = numberFrom(text);
      if (amount === null) return { ok: false, error: words.needNumber };
      let value = amount;
      if (meta.kind === "duration") value = amount * SECONDS_IN[(state.unit as DurationUnit) || "seconds"];
      if (meta.kind === "bytes") value = amount * BYTES_IN[(state.unit as ByteUnit) || "MB"];
      if (WHOLE_KINDS.includes(meta.kind)) {
        if (meta.kind === "number" || meta.kind === "percent") {
          if (!Number.isInteger(amount)) return { ok: false, error: words.needWhole };
        }
        value = Math.round(value);
      }
      return checkRange(meta, range, value, context);
    }
    case "time":
      return /^([01]\d|2[0-3]):[0-5]\d$/.test(text) ? { ok: true, value: text } : { ok: false, error: words.needTime };
    case "currency": {
      const code = text.toUpperCase();
      return /^[A-Z]{3}$/.test(code) ? { ok: true, value: code } : { ok: false, error: words.needCurrency };
    }
    case "url":
      return /^https?:\/\/\S+$/i.test(text) ? { ok: true, value: text } : { ok: false, error: words.needUrl };
    default:
      return text ? { ok: true, value: text } : { ok: false, error: words.needText };
  }
}

/** True when two stored values are the same setting value. */
export function sameValue(a: unknown, b: unknown): boolean {
  return a === b || (typeof a === "number" && typeof b === "number" && Math.abs(a - b) < 1e-9);
}

export const SECONDS_PER = SECONDS_IN;
export const BYTES_PER = BYTES_IN;

// ---------- Grouping ----------

export interface Grouped<T> {
  group: GroupId;
  label: string;
  help: string;
  items: { item: T; meta: SettingMeta }[];
}

/** Puts settings into their groups, in the order of GROUP_ORDER and then the registry's order. */
export function groupSettings<T extends { name: string; unit?: string | null; value?: unknown }>(items: T[]): Grouped<T>[] {
  const byGroup = new Map<GroupId, Grouped<T>>();
  for (const item of items) {
    const meta = metaOf(item.name, item.unit, item.value);
    let entry = byGroup.get(meta.group);
    if (!entry) {
      entry = { group: meta.group, label: groupWords[meta.group].label, help: groupWords[meta.group].help, items: [] };
      byGroup.set(meta.group, entry);
    }
    entry.items.push({ item, meta });
  }
  return GROUP_ORDER.flatMap((group) => {
    const entry = byGroup.get(group);
    return entry ? [entry] : [];
  });
}
