/**
 * A heads-up, a flag or a mistake report in the chat (HUM-2, HUM-6): it tells rather than asks, so it
 * is a quiet note (who, what, when) and not a card. The filer's words are plain text (P4). While the
 * item is still open, the one thing to do with it (acknowledge) is a small quiet button.
 */
import { AlertTriangle, Check, FileWarning, Megaphone, type LucideIcon } from "lucide-react";
import { useContext, useEffect, useState } from "react";
import { get, post } from "../api/client";
import { ErrorNote } from "../components/common";
import { formatDateTime } from "../lib/format";
import { useLoad } from "../lib/useLoad";
import { AgentText } from "../panels/board/parts";
import { t } from "../strings";
import { ItemsContext } from "./context";
import { headlineOf } from "./headline";
import type { Item } from "./logic";
import { askerOf } from "./when";

const ICONS: Record<string, LucideIcon> = { "heads-up": Megaphone, flag: AlertTriangle, "mistake report": FileWarning };

interface Props {
  itemId: number;
  /** The chat line's own text, shown until the item has loaded. */
  fallback: string;
  /** The time of the chat line, already laid out. */
  time: JSX.Element;
}

function Acknowledge({ item, onDone }: { item: Item; onDone(item: Item): void }): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const action = item.actions[0] ?? "acknowledge";
  const press = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      onDone(await post("/v1/items/decide", { project_id: item.project_id, item_id: item.id, action }));
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className="button small ghost item-note-act" disabled={busy} onClick={() => void press()}>
        <Check size={14} aria-hidden="true" />
        {t.decisions.card.actions[action] ?? action}
        <span className="visually-hidden"> {t.decisions.card.of(item.title)}</span>
      </button>
      <ErrorNote error={error} />
    </>
  );
}

export function ChatItemNote({ itemId, fallback, time }: Props): JSX.Element {
  const scope = useContext(ItemsContext);
  const projectId = scope?.projectId ?? "";
  const [view, setView] = useState<Item | null>(null);
  const [settled, setSettled] = useState(false);
  const watch = settled ? 0 : (scope?.changes ?? 0);
  const loaded = useLoad(() => get("/v1/items/show", { project_id: projectId, item_id: itemId }), [projectId, itemId, watch]);
  const item: Item | undefined = view ?? loaded.data;
  const closedAt = item?.closed_at ?? null;
  useEffect(() => {
    if (closedAt !== null) setSettled(true);
  }, [closedAt]);

  const words = t.decisions.compact.note;
  const Icon = ICONS[item?.kind ?? ""] ?? Megaphone;
  const head = item ? headlineOf(item) : null;
  const asker = item ? askerOf(item.filed_by, item.kind) : null;
  const tone = item?.kind === "flag" ? "is-warning" : "";
  const acknowledged = item?.state === "acknowledged";

  return (
    <div
      className={`item-note ${tone}`}
      data-testid="item-note"
      data-item-id={itemId}
      data-item-kind={item?.kind}
      aria-label={item ? `${head?.ask ?? ""}: ${item.title}` : undefined}
      role={item ? "group" : undefined}
    >
      <Icon size={15} aria-hidden="true" className="item-note-icon" />
      <p className="item-note-text">
        {item && head && asker ? (
          <>
            <span className="item-note-who">{item.kind === "heads-up" ? words.from(asker.who) : words.lead(head.ask)}</span>{" "}
            <AgentText text={head.subject ?? item.title} />
          </>
        ) : (
          <AgentText text={fallback} />
        )}
      </p>
      <span className="item-note-end">
        {time}
        {item && item.actions.length > 0 ? (
          <Acknowledge
            item={item}
            onDone={(next) => {
              setView(next);
              scope?.onChanged();
            }}
          />
        ) : null}
        {acknowledged ? (
          <span className="item-note-done" title={item?.closed_at ? formatDateTime(item.closed_at) : undefined}>
            <Check size={13} aria-hidden="true" />
            {words.acknowledged}
          </span>
        ) : null}
      </span>
    </div>
  );
}
