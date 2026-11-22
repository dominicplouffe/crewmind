/**
 * A list of settings, grouped and searchable, edited in place. Changes collect in a save bar that
 * asks for a reason when the scope needs one (GOV-1: the server checks it) and sends them as one
 * change. Raw names appear only behind "Show technical details".
 */
import { useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import type { Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { groupSettings, metaOf, sameValue, type GroupId, type Parsed, type StoredValue } from "../lib/settingsMeta";
import { settingsWords } from "../strings.settings";
import { SettingControl, type SettingItem } from "./SettingControl";

type View = Schemas["SettingsView"];

interface Props {
  view: View;
  /** Ask for a reason when saving (project and install settings). */
  needsReason: boolean;
  onSave(changes: Record<string, StoredValue>, reason: string): Promise<void>;
  /** Only these settings, in this order. */
  only?: string[];
  /** Leave these out (shown elsewhere). */
  exclude?: string[];
  /** Show group headings, a search box and collapsible groups. */
  grouped?: boolean;
  /** A name for the list, for screen readers. */
  label: string;
}

const SEARCH_FROM = 12;
const NOTHING: string[] = [];

export function SettingsForm({ view, needsReason, onSave, only, exclude = NOTHING, grouped = false, label }: Props): JSX.Element {
  const words = settingsWords.form;
  const formId = useId();
  const [edits, setEdits] = useState<Record<string, Parsed>>({});
  const [generation, setGeneration] = useState(0);
  const [query, setQuery] = useState("");
  const [technical, setTechnical] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [tried, setTried] = useState(false);
  const [saved, setSaved] = useState(false);
  const [closed, setClosed] = useState<Set<GroupId>>(new Set());

  const items = useMemo(() => {
    const listed = view.items.filter((item) => !exclude.includes(item.name));
    if (!only) return listed;
    return only.flatMap((name) => listed.filter((item) => item.name === name));
  }, [view.items, only, exclude]);

  const currency = useMemo(() => {
    const edited = edits["spend.currency"];
    if (edited?.ok && typeof edited.value === "string") return edited.value;
    const stored = view.items.find((item) => item.name === "spend.currency")?.value;
    return typeof stored === "string" ? stored : undefined;
  }, [edits, view.items]);

  const byName = useMemo(() => new Map(items.map((item) => [item.name, item])), [items]);
  const pending = Object.entries(edits).filter(([name, parsed]) => {
    const item = byName.get(name);
    return item !== undefined && (!parsed.ok || !sameValue(parsed.value, item.value));
  });
  const invalid = pending.some(([, parsed]) => !parsed.ok);

  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 4000);
    return () => window.clearTimeout(timer);
  }, [saved]);

  const onChange = (name: string, parsed: Parsed): void => {
    setSaved(false);
    setEdits((current) => ({ ...current, [name]: parsed }));
  };

  const discard = (): void => {
    setEdits({});
    setReason("");
    setError(null);
    setTried(false);
    setGeneration((value) => value + 1);
  };

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setTried(true);
    if (invalid || pending.length === 0) return;
    const changes: Record<string, StoredValue> = {};
    for (const [name, parsed] of pending) if (parsed.ok) changes[name] = parsed.value;
    setBusy(true);
    setError(null);
    try {
      await onSave(changes, reason.trim());
      setEdits({});
      setReason("");
      setTried(false);
      setSaved(true);
      setGeneration((value) => value + 1);
    } catch (reason_) {
      setError(reason_);
    } finally {
      setBusy(false);
    }
  };

  const needle = query.trim().toLowerCase();
  const matches = (item: SettingItem): boolean => {
    if (!needle) return true;
    const meta = metaOf(item.name, item.unit, item.value);
    const haystack = [meta.label, meta.help, ...meta.choices.map((choice) => choice.label), technical ? item.name : ""];
    return haystack.join(" ").toLowerCase().includes(needle);
  };
  const shown = items.filter(matches);
  const groups = grouped
    ? groupSettings(items)
    : [{ group: "other" as GroupId, label: "", help: "", items: items.map((item) => ({ item, meta: metaOf(item.name) })) }];

  // Rows that don't match the search are hidden, not removed, so what was typed in them is kept.
  const control = (item: SettingItem): JSX.Element => (
    <SettingControl
      key={`${item.name}-${item.version}-${generation}`}
      item={item}
      onChange={onChange}
      showError={tried}
      technical={technical}
      context={{ currency }}
      disabled={busy}
      hidden={!matches(item)}
    />
  );

  return (
    <form className="settings-form" aria-label={label} onSubmit={(event) => void submit(event)} noValidate>
      {grouped && items.length >= SEARCH_FROM ? (
        <div className="settings-search">
          <Search size={16} aria-hidden="true" />
          <label htmlFor={`${formId}-search`} className="visually-hidden">
            {words.find}
          </label>
          <input
            id={`${formId}-search`}
            type="search"
            placeholder={words.findPlaceholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      ) : null}
      {items.length === 0 ? <p className="quiet">{words.empty}</p> : null}
      {needle && shown.length === 0 ? (
        <p className="quiet settings-nomatch" role="status">
          {words.noMatch(query.trim())}
        </p>
      ) : null}
      {grouped
        ? groups.map((group) => (
            <details
              key={group.group}
              className="settings-group"
              hidden={!group.items.some(({ item }) => matches(item))}
              open={needle !== "" || !closed.has(group.group)}
              onToggle={(event) => {
                if (needle) return;
                const open = (event.currentTarget as HTMLDetailsElement).open;
                setClosed((current) => {
                  const next = new Set(current);
                  if (open) next.delete(group.group);
                  else next.add(group.group);
                  return next;
                });
              }}
            >
              <summary>
                <span className="settings-group-title">{group.label}</span>
                <span className="settings-group-help">{group.help}</span>
              </summary>
              <div className="settings-rows">{group.items.map(({ item }) => control(item))}</div>
            </details>
          ))
        : <div className="settings-rows">{items.map(control)}</div>}
      {items.length > 0 ? (
        <label className="settings-technical">
          <input type="checkbox" checked={technical} onChange={(event) => setTechnical(event.target.checked)} />
          <span>{words.technical}</span>
        </label>
      ) : null}
      <p className="visually-hidden" role="status" aria-live="polite">
        {saved ? settingsWords.common.saved : ""}
      </p>
      {pending.length > 0 || error ? (
        <div className="save-bar" role="region" aria-label={words.changes(pending.length)}>
          <p className="save-bar-count">{words.changes(pending.length)}</p>
          {needsReason ? (
            <div className="save-bar-reason">
              <label htmlFor={`${formId}-reason`}>{words.reason}</label>
              <input
                id={`${formId}-reason`}
                value={reason}
                placeholder={words.reasonPlaceholder}
                aria-describedby={`${formId}-reason-hint`}
                onChange={(event) => setReason(event.target.value)}
              />
              <p className="quiet" id={`${formId}-reason-hint`}>
                {words.reasonHint}
              </p>
            </div>
          ) : null}
          {tried && invalid ? (
            <p className="setting-error" role="alert">
              {words.fixFirst}
            </p>
          ) : null}
          <ErrorNote error={error} />
          <div className="save-bar-actions">
            <button type="button" className="button ghost" onClick={discard} disabled={busy}>
              {words.discard}
            </button>
            <button type="submit" className="button primary" disabled={busy || pending.length === 0}>
              {busy ? settingsWords.common.saving : settingsWords.common.save}
            </button>
          </div>
        </div>
      ) : saved ? (
        <p className="note note-success save-done">{settingsWords.common.saved}</p>
      ) : null}
    </form>
  );
}
