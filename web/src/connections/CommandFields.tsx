/**
 * The fields of an MCP server started from a command (CON-11): the command line, the image it
 * runs in, and each environment variable it needs, filled by a secret or variable you choose.
 * No value is typed here: a variable names a connection, read when the server starts.
 */
import { useId } from "react";
import { Plus, X } from "lucide-react";
import type { Schemas } from "../api/client";
import { connectionWords } from "../strings.connections";

type Item = Schemas["ConnectionView"];
const words = connectionWords.command;

export interface EnvRow {
  name: string;
  source: string;
}

export interface CommandValue {
  command: string;
  image: string;
  environment: EnvRow[];
}

interface Props {
  value: CommandValue;
  /** Secrets and variables the person can see, to fill a variable with. */
  sources: Item[];
  onChange(value: CommandValue): void;
}

export function environmentOf(rows: EnvRow[]): Record<string, string> {
  return Object.fromEntries(
    rows
      .filter((row) => row.name.trim() && row.source)
      .map((row) => [row.name.trim(), row.source]),
  );
}

export function CommandFields({
  value,
  sources,
  onChange,
}: Props): JSX.Element {
  const id = useId();
  const field = (part: string): string => `${id}-${part}`;
  const usable = sources.filter(
    (item) => item.kind === "secret" || item.kind === "variable",
  );
  const setRow = (index: number, row: EnvRow): void =>
    onChange({
      ...value,
      environment: value.environment.map((old, at) =>
        at === index ? row : old,
      ),
    });
  return (
    <>
      <p className="note note-warning small">{words.warning}</p>
      <div className="field">
        <label htmlFor={field("command")}>{words.command}</label>
        <input
          id={field("command")}
          value={value.command}
          onChange={(e) => onChange({ ...value, command: e.target.value })}
          required
          spellCheck={false}
          placeholder="npx -y @modelcontextprotocol/server-everything"
          aria-describedby={field("command-help")}
        />
        <p className="quiet" id={field("command-help")}>
          {words.commandHelp}
        </p>
      </div>
      <fieldset className="field env-rows">
        <legend>{words.environment}</legend>
        <p className="quiet small">{words.environmentHelp}</p>
        {value.environment.map((row, index) => (
          <div className="row env-row" key={index}>
            <label className="visually-hidden" htmlFor={field(`env-${index}`)}>
              {words.variableName(index + 1)}
            </label>
            <input
              id={field(`env-${index}`)}
              value={row.name}
              onChange={(e) => setRow(index, { ...row, name: e.target.value })}
              placeholder="GITHUB_TOKEN"
              spellCheck={false}
            />
            <label
              className="visually-hidden"
              htmlFor={field(`source-${index}`)}
            >
              {words.filledBy(row.name || String(index + 1))}
            </label>
            <select
              id={field(`source-${index}`)}
              value={row.source}
              onChange={(e) =>
                setRow(index, { ...row, source: e.target.value })
              }
            >
              <option value="">{words.choose}</option>
              {usable.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} (
                  {connectionWords.kinds[item.kind as "secret" | "variable"]})
                </option>
              ))}
            </select>
            <button
              type="button"
              className="button ghost icon"
              aria-label={words.remove(row.name || String(index + 1))}
              onClick={() =>
                onChange({
                  ...value,
                  environment: value.environment.filter(
                    (_, at) => at !== index,
                  ),
                })
              }
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        ))}
        {usable.length === 0 ? (
          <p className="quiet small">{words.noSources}</p>
        ) : null}
        <button
          type="button"
          className="button ghost"
          onClick={() =>
            onChange({
              ...value,
              environment: [...value.environment, { name: "", source: "" }],
            })
          }
        >
          <Plus size={16} aria-hidden="true" /> {words.add}
        </button>
      </fieldset>
      <details className="field">
        <summary>{words.imageLegend}</summary>
        <label htmlFor={field("image")}>{words.image}</label>
        <input
          id={field("image")}
          value={value.image}
          onChange={(e) => onChange({ ...value, image: e.target.value })}
          spellCheck={false}
          placeholder="node:22-slim"
        />
        <p className="quiet small">{words.imageHelp}</p>
      </details>
    </>
  );
}
