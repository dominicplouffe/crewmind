/**
 * The command palette (Ctrl/Cmd+K): go anywhere, open any project tool, put a slash command in the
 * message box, switch project or theme. Everything not in the main navigation is reachable here.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { t } from "../strings";
import { shell } from "../strings.shell";

export interface PaletteItem {
  key: string;
  label: string;
  detail: string;
  /** The heading the item is listed under. Defaults to `detail`. */
  group?: string;
  icon?: ReactNode;
  /** Extra words that should find this item. */
  keywords?: string;
  run(): void;
}

interface Props {
  items: PaletteItem[];
  onClose(): void;
}

export function CommandPalette({ items, onClose }: Props): JSX.Element {
  const dialog = useRef<HTMLDialogElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
  }, []);

  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return items.filter((item) => {
      const text = `${item.label} ${item.detail} ${item.group ?? ""} ${item.keywords ?? ""}`.toLowerCase();
      return words.every((word) => text.includes(word));
    });
  }, [items, query]);
  const activeIndex = Math.min(active, Math.max(0, shown.length - 1));

  const groups = useMemo(() => {
    const found: { name: string; items: { item: PaletteItem; index: number }[] }[] = [];
    shown.forEach((item, index) => {
      const name = item.group ?? item.detail;
      let group = found.find((entry) => entry.name === name);
      if (!group) {
        group = { name, items: [] };
        found.push(group);
      }
      group.items.push({ item, index });
    });
    return found;
  }, [shown]);
  // Items are numbered in the order they are shown, group by group.
  const ordered = groups.flatMap((group) => group.items.map((entry) => entry.item));

  useEffect(() => {
    list.current?.querySelector(`#palette-item-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  const run = (item: PaletteItem | undefined): void => {
    if (!item) return;
    onClose();
    item.run();
  };

  let position = -1;
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
      <div className="palette-search">
        <Search size={18} aria-hidden="true" />
        <label htmlFor="palette-input" className="visually-hidden">
          {t.palette.inputLabel}
        </label>
        <input
          id="palette-input"
          autoFocus
          value={query}
          placeholder={t.palette.placeholder}
          role="combobox"
          aria-expanded="true"
          aria-autocomplete="list"
          aria-controls="palette-list"
          aria-activedescendant={ordered.length > 0 ? `palette-item-${activeIndex}` : undefined}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              if (ordered.length === 0) return;
              const step = event.key === "ArrowDown" ? 1 : -1;
              setActive((activeIndex + step + ordered.length) % ordered.length);
            } else if (event.key === "Enter") {
              event.preventDefault();
              run(ordered[activeIndex]);
            }
          }}
        />
        <kbd>Esc</kbd>
      </div>
      <ul id="palette-list" role="listbox" aria-label={t.palette.listLabel} ref={list}>
        {groups.map((group) => (
          <li key={group.name} role="presentation">
            <div className="palette-group" aria-hidden="true">
              {group.name}
            </div>
            <ul role="group" aria-label={group.name} className="plain">
              {group.items.map(({ item }) => {
                position += 1;
                const index = position;
                return (
                  // Keyboard use goes through the input (arrows and Enter); the click is a pointer shortcut.
                  // eslint-disable-next-line jsx-a11y/click-events-have-key-events
                  <li
                    key={item.key}
                    id={`palette-item-${index}`}
                    role="option"
                    aria-selected={index === activeIndex}
                    className={index === activeIndex ? "active" : ""}
                    onClick={() => run(item)}
                    onMouseMove={() => setActive(index)}
                  >
                    <span className="palette-label">
                      {item.icon ? <span className="palette-icon">{item.icon}</span> : null}
                      <span>{item.label}</span>
                    </span>
                    <span className="quiet">{item.detail}</span>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
      {ordered.length === 0 ? (
        <p className="quiet" role="status">
          {t.palette.none}
        </p>
      ) : null}
      <footer aria-hidden="true">
        <span>
          <kbd>↑</kbd> <kbd>↓</kbd> {shell.palette.navigate}
        </span>
        <span>
          <kbd>↵</kbd> {shell.palette.run}
        </span>
        <span>
          <kbd>Esc</kbd> {shell.palette.close}
        </span>
      </footer>
    </dialog>
  );
}
