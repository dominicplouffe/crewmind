/** The "More" menu on a message: a menu button that keeps the less common actions out of the way. */
import { MoreHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { t } from "../strings";

export interface MenuAction {
  key: string;
  label: string;
  run(): void;
}

export function MessageMenu({ author, actions }: { author: string; actions: MenuAction[] }): JSX.Element | null {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    list.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onPointer = (event: PointerEvent): void => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  if (actions.length === 0) return null;

  const closeToTrigger = (): void => {
    setOpen(false);
    trigger.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const items = Array.from(list.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = (at + 1) % items.length;
    else if (event.key === "ArrowUp") next = (at - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeToTrigger();
    } else if (event.key === "Tab") setOpen(false);
    if (next !== null) {
      event.preventDefault();
      items[next]?.focus();
    }
  };

  return (
    <span className="message-menu-wrap" ref={wrap}>
      <button
        type="button"
        className="message-action"
        title={t.listening.more}
        ref={trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <MoreHorizontal size={15} aria-hidden="true" />
        <span className="visually-hidden">
          {t.listening.more} {t.listening.moreFor(author)}
        </span>
      </button>
      {open ? (
        <div
          className="message-menu"
          role="menu"
          tabIndex={-1}
          id={id}
          ref={list}
          aria-label={t.listening.menuLabel}
          onKeyDown={onKeyDown}
        >
          {actions.map((action) => (
            <button
              key={action.key}
              type="button"
              role="menuitem"
              tabIndex={-1}
              onClick={() => {
                closeToTrigger();
                action.run();
              }}
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </span>
  );
}
