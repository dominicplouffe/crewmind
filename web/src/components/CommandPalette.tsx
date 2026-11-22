/** The command palette (Ctrl/Cmd+K): open a panel, put a slash command in the message box, switch project or theme. */
import { useEffect, useMemo, useRef, useState } from "react";
import { t } from "../strings";

export interface PaletteItem {
  key: string;
  label: string;
  detail: string;
  run(): void;
}

interface Props {
  items: PaletteItem[];
  onClose(): void;
}

export function CommandPalette({ items, onClose }: Props): JSX.Element {
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
  }, []);

  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return items.filter((item) => {
      const text = `${item.label} ${item.detail}`.toLowerCase();
      return words.every((word) => text.includes(word));
    });
  }, [items, query]);
  const activeIndex = Math.min(active, Math.max(0, shown.length - 1));

  const run = (item: PaletteItem | undefined): void => {
    if (!item) return;
    onClose();
    item.run();
  };

  return (
    // Clicking the backdrop closes the dialog; Esc does the same for keyboard users.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={dialog}
      className="palette"
      aria-label={t.palette.title}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <label htmlFor="palette-input" className="visually-hidden">
        {t.palette.inputLabel}
      </label>
      <input
        id="palette-input"
        autoFocus
        value={query}
        placeholder={t.palette.placeholder}
        aria-autocomplete="list"
        aria-controls="palette-list"
        aria-activedescendant={shown.length > 0 ? `palette-item-${activeIndex}` : undefined}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (shown.length === 0) return;
            const step = event.key === "ArrowDown" ? 1 : -1;
            setActive((activeIndex + step + shown.length) % shown.length);
          } else if (event.key === "Enter") {
            event.preventDefault();
            run(shown[activeIndex]);
          }
        }}
      />
      <ul id="palette-list" role="listbox" aria-label={t.palette.listLabel}>
        {shown.map((item, index) => (
          // Keyboard use goes through the input (arrows and Enter); the click is a pointer shortcut.
          // eslint-disable-next-line jsx-a11y/click-events-have-key-events
          <li
            key={item.key}
            id={`palette-item-${index}`}
            role="option"
            aria-selected={index === activeIndex}
            className={index === activeIndex ? "active" : ""}
            onClick={() => run(item)}
          >
            <span>{item.label}</span>
            <span className="quiet">{item.detail}</span>
          </li>
        ))}
      </ul>
      {shown.length === 0 ? (
        <p className="quiet" role="status">
          {t.palette.none}
        </p>
      ) : null}
    </dialog>
  );
}
