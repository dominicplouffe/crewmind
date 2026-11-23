/**
 * Plain words for numbers and times (P18): "1.9K tokens", "4 min ago", "in 2 days".
 * Presentation only: no rule or threshold lives here.
 */
const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat();
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto", style: "long" });

/** 1920 → "1.9K", 20000000 → "20M". Small numbers are written out. */
export function compactNumber(value: number): string {
  return Math.abs(value) < 10000 ? whole.format(value) : compact.format(value);
}

export function tokens(value: number): string {
  return `${compactNumber(value)} ${value === 1 ? "token" : "tokens"}`;
}

/** Share of a whole as a percentage with sensible precision: "<1%", "0.4%", "37%". */
export function share(part: number, total: number): string {
  if (total <= 0) return "0%";
  const value = (part / total) * 100;
  if (value === 0) return "0%";
  if (value < 0.1) return "<0.1%";
  if (value < 10) return `${value.toFixed(1).replace(/\.0$/, "")}%`;
  return `${Math.round(value)}%`;
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
  ["second", 1],
];

/** "4 minutes ago", "in 3 hours", "now". */
export function fromNow(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "";
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return iso;
  const seconds = Math.round((at - now) / 1000);
  if (Math.abs(seconds) < 45) return "just now";
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

/** A length of time in words: "45 min", "1 h 30 min", "2 days". */
export function duration(seconds: number): string {
  const value = Math.max(0, Math.round(seconds));
  if (value < 60) return `${value} s`;
  const minutes = Math.round(value / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours < 48) return rest ? `${hours} h ${rest} min` : `${hours} h`;
  const days = Math.round(hours / 24);
  return `${days} days`;
}

/** "Good morning", "Good afternoon" or "Good evening", by the local hour. */
export function greeting(date: Date = new Date()): string {
  const hour = date.getHours();
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/** The first name, for a greeting. */
export function firstName(name: string | undefined | null): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}
