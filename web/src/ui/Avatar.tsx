/**
 * Avatars. Agents are rounded squares and people are circles, so the two are never confused,
 * and the shape carries the difference as well as the label (never colour alone).
 * The hue is picked from the name, so an agent keeps its colour everywhere.
 */
const HUES = 8;

export function hueOf(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return (hash % HUES) + 1;
}

export function initialsOf(name: string): string {
  const words = name
    .replace(/[-_.]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  const [first, second] = words;
  if (first === undefined) return "?";
  if (second === undefined) {
    // "CEO" stays "CE"; "writer2" becomes "W2".
    const digits = first.match(/\d+$/)?.[0] ?? "";
    return (first.slice(0, digits ? 1 : 2) + digits).slice(0, 2).toUpperCase();
  }
  return (first.charAt(0) + second.charAt(0)).toUpperCase();
}

interface Props {
  name: string;
  /** What picks the colour, when it is not the name: an agent's seat, so a rename keeps its colour. */
  hueKey?: string;
  kind?: "agent" | "person";
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  /** Shown as a small dot on the corner; the label is given elsewhere in text. */
  status?: "working" | "waiting" | "blocked" | "idle" | null;
  label?: string;
}

export function Avatar({ name, hueKey, kind = "agent", size = "md", status = null, label }: Props): JSX.Element {
  const hue = hueOf(hueKey ?? name);
  return (
    <span
      className={`avatar avatar-${kind} avatar-${size}`}
      style={{ background: `var(--avatar-${hue}-bg)`, color: `var(--avatar-${hue}-fg)` }}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {initialsOf(name)}
      {status ? <span className={`avatar-status status-${status}`} /> : null}
    </span>
  );
}
