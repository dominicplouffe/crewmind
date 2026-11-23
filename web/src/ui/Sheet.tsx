/**
 * A wide sheet that slides in from the right on a desktop and up from the bottom on a phone.
 * Built on <dialog> so focus is trapped, Esc closes it and the page behind is inert.
 * Detail views get real room here instead of a squeezed side column.
 */
import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { t } from "../strings";

interface Props {
  title: string;
  /** A line under the title. */
  subtitle?: ReactNode;
  onClose(): void;
  children: ReactNode;
  /** Controls placed beside the title. */
  actions?: ReactNode;
  size?: "md" | "lg" | "xl";
  testId?: string;
}

export function Sheet({ title, subtitle, onClose, children, actions, size = "lg", testId = "sheet" }: Props): JSX.Element {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    heading.current?.focus();
  }, []);

  return (
    // Clicking the backdrop closes the sheet; Esc does the same (the dialog's cancel event).
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={dialog}
      className={`sheet sheet-${size}`}
      aria-labelledby="sheet-title"
      data-testid={testId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <div className="sheet-inner">
        <header className="sheet-head">
          <div className="sheet-titles">
            <h2 id="sheet-title" tabIndex={-1} ref={heading}>
              {title}
            </h2>
            {subtitle ? <div className="quiet">{subtitle}</div> : null}
          </div>
          {actions}
          <button type="button" className="button ghost icon-only" onClick={onClose} aria-label={t.panels.close}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="sheet-body">{children}</div>
      </div>
    </dialog>
  );
}
