/** A small modal dialog with a heading. Esc closes it; focus goes back to where it was. */
import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  title: string;
  testId?: string;
  onClose(): void;
  children: ReactNode;
}

export function Modal({ title, testId, onClose, children }: Props): JSX.Element {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();

  useEffect(() => {
    const before = document.activeElement;
    const element = dialog.current;
    if (element && !element.open) element.showModal();
    return () => {
      if (before instanceof HTMLElement && before.isConnected) before.focus();
    };
  }, []);

  return (
    <dialog ref={dialog} className="modal" aria-labelledby={id} data-testid={testId} onClose={onClose}>
      <h2 id={id}>{title}</h2>
      {children}
    </dialog>
  );
}
