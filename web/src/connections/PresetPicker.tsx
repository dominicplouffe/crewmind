/**
 * Start from a well-known MCP server (CON-15): choosing one fills in the address or command, how
 * Nightsquad signs in, and says which secret to create at the provider. Nothing is saved by choosing.
 */
import { useEffect, useId, useState } from "react";
import { get, type Schemas } from "../api/client";
import { connectionWords } from "../strings.connections";

export type Preset = Schemas["Preset"];
const words = connectionWords.presets;

interface Props {
  onChoose(preset: Preset | null): void;
}

export function PresetPicker({ onChoose }: Props): JSX.Element | null {
  const id = useId();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [chosen, setChosen] = useState("");

  useEffect(() => {
    let live = true;
    get("/v1/connections/presets")
      .then((list) => live && setPresets(list.presets ?? []))
      .catch(() => live && setPresets([]));
    return () => {
      live = false;
    };
  }, []);

  if (presets.length === 0) return null;
  const preset = presets.find((item) => item.slug === chosen) ?? null;
  return (
    <div className="field preset-picker">
      <label htmlFor={id}>{words.label}</label>
      <select
        id={id}
        value={chosen}
        onChange={(event) => {
          setChosen(event.target.value);
          onChoose(presets.find((item) => item.slug === event.target.value) ?? null);
        }}
      >
        <option value="">{words.none}</option>
        {presets.map((item) => (
          <option key={item.slug} value={item.slug}>
            {item.title}
          </option>
        ))}
      </select>
      {preset ? (
        <div className="note note-info small" data-testid="preset-note">
          <p>{preset.description}</p>
          {preset.value_needed ? <p>{words.secret(preset.value_needed.description)}</p> : null}
          {(preset.environment ?? []).map((variable) => (
            <p key={variable.env}>{words.variable(variable.env, variable.description)}</p>
          ))}
          {preset.docs ? (
            <p>
              <a href={preset.docs} target="_blank" rel="noopener noreferrer">
                {words.docs(preset.title)}
                <span className="visually-hidden"> {words.newTab}</span>
              </a>
            </p>
          ) : null}
        </div>
      ) : (
        <p className="quiet small">{words.help}</p>
      )}
    </div>
  );
}
