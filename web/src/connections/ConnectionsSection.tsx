/**
 * Settings → Connections (CON-15): your own secrets and variables, and the install's. The empty
 * state explains the kinds; one Add flow serves both; `.env` lines can be pasted at once.
 */
import { useState } from "react";
import { Braces, ClipboardPaste, KeyRound, Plus, Send } from "lucide-react";
import { get, type Schemas } from "../api/client";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/common";
import { useLoad } from "../lib/useLoad";
import { connectionWords as words } from "../strings.connections";
import { Skeleton } from "../ui/Skeleton";
import { AddSheet } from "./AddSheet";
import { ImportSheet } from "./ImportSheet";
import { ItemRow } from "./ItemRow";

type Item = Schemas["ConnectionView"];
type Tab = "person" | "install";

export function EmptyKinds({ onAdd }: { onAdd(kind: "secret" | "variable"): void }): JSX.Element {
  const cards = [
    { key: "send", icon: <Send size={20} />, ...words.empty.secret, kind: "secret" as const },
    { key: "given", icon: <KeyRound size={20} />, ...words.empty.given, kind: "secret" as const },
    { key: "variable", icon: <Braces size={20} />, ...words.empty.variable, kind: "variable" as const },
  ];
  return (
    <div className="connection-empty" data-testid="connections-empty">
      <p className="quiet">{words.intro}</p>
      <ul className="kind-cards plain">
        {cards.map((card) => (
          <li key={card.key} className="kind-card">
            <span className="kind-card-icon" aria-hidden="true">
              {card.icon}
            </span>
            <p className="kind-card-title">{card.title}</p>
            <p className="quiet small">{card.help}</p>
            <button type="button" className="button small" onClick={() => onAdd(card.kind)}>
              {words.add}
              <span className="visually-hidden"> {card.title}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ConnectionsSection(): JSX.Element {
  const { person } = useAuth();
  const isAdmin = person?.role === "admin";
  const [tab, setTab] = useState<Tab>("person");
  const [adding, setAdding] = useState<"secret" | "variable" | null>(null);
  const [importing, setImporting] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const list = useLoad(() => get("/v1/connections/list", { scope: tab }), [tab]);
  const items: Item[] = list.data?.items ?? [];
  const canAdd = tab === "person" || isAdmin;

  return (
    <section className="card settings-card" aria-labelledby="connections-title">
      <div className="settings-card-head with-action">
        <div>
          <h3 id="connections-title">{words.listTitle[tab]}</h3>
          <p className="quiet">{words.scopeHelp[tab]}</p>
        </div>
        {canAdd && items.length > 0 ? (
          <div className="row">
            <button type="button" className="button" onClick={() => setImporting(true)}>
              <ClipboardPaste size={16} aria-hidden="true" />
              {words.pasteEnv}
            </button>
            <button type="button" className="button primary" onClick={() => setAdding("secret")}>
              <Plus size={16} aria-hidden="true" />
              {words.add}
            </button>
          </div>
        ) : null}
      </div>
      <div className="segmented" role="tablist" aria-label={words.sectionTitle}>
        {(["person", "install"] as const).map((option) => (
          <button
            key={option}
            type="button"
            role="tab"
            aria-selected={tab === option}
            className={tab === option ? "active" : ""}
            onClick={() => setTab(option)}
          >
            {words.scopes[option]}
          </button>
        ))}
      </div>
      {saved ? (
        <p className="note note-success" role="status">
          {saved}
        </p>
      ) : null}
      <ErrorNote error={list.error} />
      {list.loading && !list.data ? <Skeleton lines={3} block /> : null}
      {list.data && items.length === 0 ? (
        canAdd ? (
          <>
            <EmptyKinds onAdd={setAdding} />
            <button type="button" className="button ghost small" onClick={() => setImporting(true)}>
              <ClipboardPaste size={16} aria-hidden="true" />
              {words.pasteEnv}
            </button>
          </>
        ) : (
          <p className="quiet">{words.empty.title}</p>
        )
      ) : null}
      {items.length > 0 ? (
        <ul className="connection-list plain" data-testid="connection-list">
          {items.map((item) => (
            <ItemRow key={item.id} item={item} onChanged={list.reload} />
          ))}
        </ul>
      ) : null}
      {adding ? (
        <AddSheet
          context={{ mode: "settings", scope: tab }}
          startKind={adding}
          onClose={() => setAdding(null)}
          onSaved={(item) => {
            setAdding(null);
            setSaved(words.saved(item.name));
            list.reload();
          }}
        />
      ) : null}
      {importing ? (
        <ImportSheet
          scope={tab}
          onClose={() => setImporting(false)}
          onSaved={(count) => {
            setImporting(false);
            setSaved(words.importSaved(count));
            list.reload();
          }}
        />
      ) : null}
    </section>
  );
}
