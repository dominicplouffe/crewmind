/**
 * One labelled control for one setting: the right input for its kind, shown in a unit people use
 * (minutes, not seconds; "3M", not 3000000), with its help and allowed range in words. What is
 * typed is checked in the same units and handed up as the value the server stores.
 */
import { useId, useMemo, useState } from "react";
import type { Schemas } from "../api/client";
import {
  durationUnitsFor,
  editStateOf,
  metaOf,
  parseAllowed,
  rangeText,
  valueOf,
  type EditState,
  type FormatContext,
  type Parsed,
  type SettingMeta,
} from "../lib/settingsMeta";
import { settingsWords, unitWords } from "../strings.settings";

export type SettingItem = Schemas["SettingItem"];

interface Props {
  item: SettingItem;
  /** Called on every edit with the stored value, or what is wrong. */
  onChange(name: string, parsed: Parsed): void;
  /** Show the error even before the field loses focus (after a save was tried). */
  showError?: boolean;
  /** Show the raw name, stored value and allowed text. */
  technical?: boolean;
  context?: FormatContext;
  disabled?: boolean;
  /** Kept mounted but out of sight (filtered out by a search). */
  hidden?: boolean;
}

let zones: string[] | null = null;
function timeZones(): string[] {
  if (zones) return zones;
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  try {
    zones = intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
  } catch {
    zones = [];
  }
  return zones;
}

function suffixOf(meta: SettingMeta, context: FormatContext, amount: string): string | null {
  const one = amount.trim() === "1";
  switch (meta.kind) {
    case "percent":
      return "%";
    case "tokens":
      return unitWords.tokens[1];
    case "money":
      return context.currency ?? null;
    case "number":
      return meta.noun ? (one ? meta.noun[0] : meta.noun[1]) : null;
    default:
      return null;
  }
}

export function SettingControl({ item, onChange, showError = false, technical = false, context = {}, disabled = false, hidden = false }: Props): JSX.Element {
  const words = settingsWords.control;
  const meta = useMemo(() => metaOf(item.name, item.unit, item.value), [item.name, item.unit, item.value]);
  const range = useMemo(() => parseAllowed(item.allowed, item.unit), [item.allowed, item.unit]);
  const [state, setState] = useState<EditState>(() => editStateOf(meta, range, item.value));
  const [touched, setTouched] = useState(false);
  const id = useId();
  const inputId = `${id}-input`;
  const labelId = `${id}-label`;
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;

  const parsed = valueOf(meta, range, state, context);
  const error = !parsed.ok && (touched || showError) ? parsed.error : null;
  const described = [helpId, error ? errorId : null].filter(Boolean).join(" ");
  const off = meta.special !== null && state.special;

  const update = (next: Partial<EditState>): void => {
    const merged = { ...state, ...next };
    setState(merged);
    onChange(item.name, valueOf(meta, range, merged, context));
  };

  const toggleSpecial = (checked: boolean): void => {
    if (!checked && state.text.trim() === "") {
      // Coming back from "off": start from the smallest allowed value, or a sensible blank.
      const start = range.min !== undefined ? editStateOf(meta, range, range.min) : editStateOf(meta, range, meta.kind === "time" ? "08:00" : "");
      update({ special: false, text: start.text, unit: start.unit || state.unit });
      return;
    }
    update({ special: checked });
  };

  const range_ = rangeText(meta, range, context);
  const help = [meta.help, range_ && !meta.help.includes(range_) ? `${range_}.` : ""].filter(Boolean).join(" ");
  const inputProps = {
    id: inputId,
    disabled: disabled || off,
    "aria-describedby": described,
    "aria-invalid": error ? true : undefined,
    onBlur: () => setTouched(true),
  };

  let control: JSX.Element;
  switch (meta.kind) {
    case "toggle": {
      const on = state.text === "on";
      control = (
        <button
          type="button"
          role="switch"
          id={inputId}
          className="switch"
          aria-checked={on}
          aria-labelledby={labelId}
          aria-describedby={helpId}
          disabled={disabled}
          onClick={() => update({ text: on ? "off" : "on" })}
        >
          <span className="switch-track" aria-hidden="true">
            <span className="switch-thumb" />
          </span>
          <span className="switch-text">{on ? words.on : words.off}</span>
        </button>
      );
      break;
    }
    case "choice": {
      const options = meta.choices.some((choice) => choice.value === state.text)
        ? meta.choices
        : [...meta.choices, { value: state.text, label: state.text }];
      const short = options.length <= 3 && options.every((choice) => choice.label.length <= 22);
      control = short ? (
        <div className="segmented" role="radiogroup" aria-labelledby={labelId} aria-describedby={helpId}>
          {options.map((choice) => (
            <label key={choice.value} className="segment">
              <input
                type="radio"
                name={inputId}
                value={choice.value}
                checked={state.text === choice.value}
                disabled={disabled}
                onChange={() => update({ text: choice.value })}
              />
              <span>{choice.label}</span>
            </label>
          ))}
        </div>
      ) : (
        <select {...inputProps} aria-labelledby={labelId} value={state.text} onChange={(event) => update({ text: event.target.value })}>
          {options.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
      );
      break;
    }
    case "duration":
    case "bytes": {
      const units: string[] =
        meta.kind === "bytes" ? ["MB", "GB"] : durationUnitsFor(range, typeof item.value === "number" ? item.value : undefined);
      const one = state.text.trim() === "1";
      const unitLabel = (unit: string): string => {
        const pair = unitWords[unit as keyof typeof unitWords];
        return pair ? (one ? pair[0] : pair[1]) : unit;
      };
      control = (
        <div className="amount">
          <input
            {...inputProps}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={state.text}
            onChange={(event) => update({ text: event.target.value })}
          />
          {units.length > 1 ? (
            <select
              aria-label={settingsWords.control.unit(meta.label)}
              value={state.unit}
              disabled={disabled || off}
              onChange={(event) => update({ unit: event.target.value })}
            >
              {units.map((unit) => (
                <option key={unit} value={unit}>
                  {unitLabel(unit)}
                </option>
              ))}
            </select>
          ) : (
            <span className="amount-suffix" aria-hidden="true">
              {unitLabel(units[0] ?? state.unit)}
            </span>
          )}
        </div>
      );
      break;
    }
    case "time":
      control = <input {...inputProps} type="time" className="setting-short" value={state.text} onChange={(event) => update({ text: event.target.value })} />;
      break;
    case "timezone": {
      const list = timeZones();
      control =
        list.length > 0 ? (
          <select {...inputProps} value={state.text} onChange={(event) => update({ text: event.target.value })}>
            {list.includes(state.text) ? null : <option value={state.text}>{state.text || words.choose}</option>}
            {list.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        ) : (
          <input {...inputProps} type="text" value={state.text} onChange={(event) => update({ text: event.target.value })} />
        );
      break;
    }
    case "url":
      control = (
        <input
          {...inputProps}
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://"
          value={state.text}
          onChange={(event) => update({ text: event.target.value })}
        />
      );
      break;
    case "currency":
      control = (
        <input
          {...inputProps}
          type="text"
          className="setting-short"
          maxLength={3}
          autoComplete="off"
          spellCheck={false}
          value={state.text}
          onChange={(event) => update({ text: event.target.value.toUpperCase() })}
        />
      );
      break;
    case "text":
      control = <input {...inputProps} type="text" value={state.text} onChange={(event) => update({ text: event.target.value })} />;
      break;
    default: {
      const suffix = suffixOf(meta, context, state.text);
      control = (
        <div className="amount">
          <input
            {...inputProps}
            type="text"
            inputMode={meta.kind === "money" ? "decimal" : meta.kind === "tokens" ? "text" : "numeric"}
            autoComplete="off"
            value={state.text}
            onChange={(event) => update({ text: event.target.value })}
          />
          {suffix ? (
            <span className="amount-suffix" aria-hidden="true">
              {suffix}
            </span>
          ) : null}
        </div>
      );
    }
  }

  const labelled = meta.kind !== "toggle" && meta.kind !== "choice";
  return (
    <div className="setting-row" data-testid={`setting-${item.name}`} data-invalid={error ? "true" : undefined} hidden={hidden}>
      <div className="setting-text">
        {labelled ? (
          <label htmlFor={inputId} id={labelId} className="setting-label">
            {meta.label}
          </label>
        ) : (
          <span id={labelId} className="setting-label">
            {meta.label}
          </span>
        )}
        <p className="setting-help" id={helpId}>
          {help}
          {meta.kind === "tokens" ? ` ${words.tokensHint}` : ""}
        </p>
      </div>
      <div className="setting-input">
        {control}
        {meta.special ? (
          <label className="setting-check">
            <input type="checkbox" checked={state.special} disabled={disabled} onChange={(event) => toggleSpecial(event.target.checked)} />
            <span>{meta.special.toggle}</span>
          </label>
        ) : null}
        {error ? (
          <p className="setting-error" id={errorId}>
            {error}
          </p>
        ) : null}
      </div>
      {technical ? (
        <p className="setting-tech">
          <code>{settingsWords.form.technicalLine(item.name, JSON.stringify(item.value), item.unit)}</code>
          <span>{settingsWords.form.allowed(item.allowed)}</span>
        </p>
      ) : null}
    </div>
  );
}
