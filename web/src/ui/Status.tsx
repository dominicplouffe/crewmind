/** A status pill: a dot and a word. The word always carries the meaning (WCAG 1.4.1). */
import type { ReactNode } from "react";

export type Tone = "accent" | "success" | "warning" | "danger" | "neutral" | "info";

export function Pill({ tone = "neutral", children, dot = true, live = false }: { tone?: Tone; children: ReactNode; dot?: boolean; live?: boolean }): JSX.Element {
  return (
    <span className={`pill pill-${tone}`}>
      {dot ? <span className={live ? "pill-dot live" : "pill-dot"} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
