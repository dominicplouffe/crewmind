/** A list of remembered facts or preferences, each with its source, date and actions. */
import { useState } from "react";
import type { MemoryEntry } from "../../api/client";
import { formatDateTime } from "../../lib/format";
import { t } from "../../strings";
import { Tag, TextForm } from "./parts";

interface Props {
  label: string;
  items: MemoryEntry[];
  busy: boolean;
  showScope?: boolean;
  /** Left out where a fact cannot be edited or pinned (your preferences). */
  onEdit?(entry: MemoryEntry, text: string): Promise<unknown>;
  onPin?(entry: MemoryEntry): void;
  onForget(entry: MemoryEntry): void;
}

export function EntryList({ label, items, busy, showScope, onEdit, onPin, onForget }: Props): JSX.Element {
  const [editing, setEditing] = useState<string | null>(null);
  const [forgetting, setForgetting] = useState<string | null>(null);
  const words = t.memory.recall;

  return (
    <ul className="records plain" aria-label={label}>
      {items.map((entry) => {
        const when = formatDateTime(entry.at);
        const name = <span className="visually-hidden"> {entry.text}</span>;
        return (
          <li key={entry.id} data-testid="memory-entry">
            <p className="record-text">{entry.text}</p>
            <p className="quiet">
              {showScope ? <Tag>{entry.scope}</Tag> : null}{" "}
              {entry.untrusted ? <Tag title={words.untrustedHint}>{words.untrusted}</Tag> : null}{" "}
              {entry.source ? words.source(entry.source, when) : words.noSource(when)}
            </p>
            {editing === entry.id && onEdit ? (
              <TextForm
                label={words.editLabel}
                submit={t.memory.save}
                initial={entry.text}
                multiline
                focus
                onCancel={() => setEditing(null)}
                onSubmit={async (text) => {
                  await onEdit(entry, text);
                  setEditing(null);
                }}
              />
            ) : forgetting === entry.id ? (
              <div className="note" role="group" aria-label={words.forgetSure}>
                <p>{words.forgetSure}</p>
                <div className="row wrap">
                  <button
                    type="button"
                    className="button small primary"
                    disabled={busy}
                    onClick={() => {
                      setForgetting(null);
                      onForget(entry);
                    }}
                  >
                    {words.forgetYes}
                  </button>
                  <button type="button" className="button small" onClick={() => setForgetting(null)}>
                    {t.common.cancel}
                  </button>
                </div>
              </div>
            ) : (
              <div className="row wrap">
                {onEdit ? (
                  <button type="button" className="button small" onClick={() => setEditing(entry.id)}>
                    {words.edit}
                    {name}
                  </button>
                ) : null}
                {onPin ? (
                  <button type="button" className="button small" disabled={busy} onClick={() => onPin(entry)}>
                    {words.pin}
                    {name}
                  </button>
                ) : null}
                <button type="button" className="button small" onClick={() => setForgetting(entry.id)}>
                  {words.forget}
                  {name}
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
