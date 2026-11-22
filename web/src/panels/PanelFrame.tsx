/** The frame every side panel shares: a heading that takes focus, and a close button. */
import { useEffect, useRef, type ReactNode } from "react";
import { t } from "../strings";

interface Props {
  title: string;
  onClose(): void;
  children: ReactNode;
}

export function PanelFrame({ title, onClose, children }: Props): JSX.Element {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
  }, [title]);

  return (
    // Esc closes the panel from any control inside it; the close button does the same.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <aside
      className="panel"
      aria-labelledby="panel-title"
      data-testid="panel"
      onKeyDown={(event) => {
        if (event.key === "Escape" && !event.defaultPrevented) onClose();
      }}
    >
      <header className="panel-head">
        <h2 id="panel-title" tabIndex={-1} ref={heading}>
          {title}
        </h2>
        <button type="button" className="button small" onClick={onClose}>
          {t.panels.close}
        </button>
      </header>
      {/* The body scrolls, so keyboard users must be able to focus it (WCAG 2.1.1). */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className="panel-body" tabIndex={0}>
        {children}
      </div>
    </aside>
  );
}
