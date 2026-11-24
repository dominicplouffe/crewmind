/**
 * The Nightsquad mark and wordmark (docs/design/brand.md). The mark is a crew around one mind:
 * three members joined to a centre, inside a rounded tile. It reads at 16px and works in one colour.
 */
import { t } from "../strings";

export function LogoMark({ size = 24, title }: { size?: number; title?: string }): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      className="logo-mark"
    >
      <rect width="32" height="32" rx="8" fill="var(--color-accent)" />
      <g stroke="var(--color-accent-text)" strokeWidth="2" strokeLinecap="round" opacity="0.55">
        <path d="M16 16 9.5 10M16 16l6.5-6M16 16v7.5" />
      </g>
      <g fill="var(--color-accent-text)">
        <circle cx="16" cy="16" r="3.6" />
        <circle cx="9" cy="9.5" r="2.4" />
        <circle cx="23" cy="9.5" r="2.4" />
        <circle cx="16" cy="24.5" r="2.4" />
      </g>
    </svg>
  );
}

export function Logo({ size = 24 }: { size?: number }): JSX.Element {
  return (
    <span className="logo">
      <LogoMark size={size} />
      <span className="logo-word">{t.app.name}</span>
    </span>
  );
}
