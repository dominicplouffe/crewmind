/**
 * A menu button (WAI-ARIA menu button pattern): opens a list of actions, arrow keys move,
 * Enter or Space runs one, Esc closes and returns focus to the button.
 */
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface MenuItem {
  key: string;
  label: string;
  icon?: ReactNode;
  detail?: string;
  /** Marks the current choice in a group (for example the theme). */
  checked?: boolean;
  danger?: boolean;
  run(): void;
}

interface Props {
  label: string;
  button: ReactNode;
  items: (MenuItem | "separator")[];
  className?: string;
  align?: "start" | "end";
  placement?: "below" | "above";
  testId?: string;
  /** False when the button shows its own words: its name then comes from them (WCAG 2.5.3). */
  labelButton?: boolean;
}

export function Menu({
  label,
  button,
  items,
  className = "button ghost",
  align = "end",
  placement = "below",
  testId,
  labelButton = true,
}: Props): JSX.Element {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const actions = items.filter((item): item is MenuItem => item !== "separator");

  useEffect(() => {
    if (!open) return;
    list.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]')[active]?.focus();
  }, [open, active]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent): void => {
      if (!list.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const shut = (): void => {
    setOpen(false);
    trigger.current?.focus();
  };

  let index = -1;
  return (
    <span className="menu">
      <button
        ref={trigger}
        type="button"
        className={className}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label={labelButton ? label : undefined}
        data-testid={testId}
        onClick={() => {
          setActive(0);
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setActive(event.key === "ArrowDown" ? 0 : actions.length - 1);
            setOpen(true);
          }
        }}
      >
        {button}
      </button>
      {open ? (
        <ul
          ref={list}
          id={id}
          role="menu"
          aria-label={label}
          className={`menu-list menu-${align} menu-${placement}`}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              shut();
            } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              const step = event.key === "ArrowDown" ? 1 : -1;
              setActive((value) => (value + step + actions.length) % actions.length);
            } else if (event.key === "Home") {
              setActive(0);
            } else if (event.key === "End") {
              setActive(actions.length - 1);
            } else if (event.key === "Tab") {
              setOpen(false);
            }
          }}
        >
          {items.map((item, position) => {
            if (item === "separator") return <li key={`sep-${position}`} role="separator" className="menu-sep" />;
            index += 1;
            const mine = index;
            return (
              // The role is menuitem or menuitemradio (both interactive); the rule cannot read a role chosen at run time.
              // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
              <li
                key={item.key}
                role={item.checked === undefined ? "menuitem" : "menuitemradio"}
                aria-checked={item.checked}
                tabIndex={mine === active ? 0 : -1}
                className={item.danger ? "menu-item danger" : "menu-item"}
                onClick={() => {
                  setOpen(false);
                  item.run();
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setOpen(false);
                    item.run();
                  }
                }}
              >
                {item.icon ? <span className="menu-icon">{item.icon}</span> : null}
                <span className="menu-label">{item.label}</span>
                {item.detail ? <span className="menu-detail">{item.detail}</span> : null}
                {item.checked ? <span className="menu-check" aria-hidden="true">✓</span> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </span>
  );
}
