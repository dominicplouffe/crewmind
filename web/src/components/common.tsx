/** Small shared pieces: error notes, loading lines, empty states, safe markdown. */
import { useMemo, type ReactNode } from "react";
import { ApiError } from "../api/client";
import { renderMarkdown } from "../lib/markdown";
import { t } from "../strings";

/** Shows what went wrong and the next step, in the server's own words when it gave them. */
export function ErrorNote({ error }: { error: unknown }): JSX.Element | null {
  if (!error) return null;
  const api = error instanceof ApiError ? error : null;
  const message = api?.message ?? t.errors.network;
  const hint = api ? api.hint : t.errors.networkHint;
  return (
    <div className="note note-error" role="alert">
      <p className="note-title">{message}</p>
      {hint ? <p className="note-hint">{hint}</p> : null}
    </div>
  );
}

export function Loading({ label = t.common.loading }: { label?: string }): JSX.Element {
  return (
    <p className="quiet" role="status">
      {label}
    </p>
  );
}

export function Empty({ title, next }: { title: string; next: string }): JSX.Element {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      <p className="quiet">{next}</p>
    </div>
  );
}

/** Renders untrusted markdown. The HTML is sanitized by `renderMarkdown` before it is set. */
export function Markdown({ source, className }: { source: string; className?: string }): JSX.Element {
  const html = useMemo(() => renderMarkdown(source), [source]);
  return <div className={`markdown ${className ?? ""}`} dangerouslySetInnerHTML={{ __html: html }} />;
}

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint ? (
        <p className="quiet" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Preformatted text that keyboard users can scroll: scrollable regions must take focus (WCAG 2.1.1). */
export function Pre({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <pre tabIndex={0} className={className}>
      {children}
    </pre>
  );
}
