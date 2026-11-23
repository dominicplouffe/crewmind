/**
 * An MCP server's tools (CON-12, INT-4): what each does in the server's own words (shown as
 * data), whether it only reads or may change things, and a switch to allow it. Allowing a tool
 * that changes things asks once, in plain words.
 */
import { useState } from "react";
import { post, type Schemas } from "../api/client";
import { ErrorNote } from "../components/common";
import { Modal } from "../components/Modal";
import { connectionWords } from "../strings.connections";
import { Pill } from "../ui/Status";

type Item = Schemas["ConnectionView"];
type Tool = Schemas["McpToolView"];

const words = connectionWords.mcp;

interface Props {
  item: Item;
  onChanged(): void;
}

export function McpTools({ item, onChanged }: Props): JSX.Element | null {
  const [asking, setAsking] = useState<Tool | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const tools = item.mcp?.tools ?? [];
  if (tools.length === 0) return null;

  const set = (tool: Tool, allowed: boolean): void => {
    setBusy(tool.name);
    setError(null);
    const path = allowed ? "/v1/connections/allow_tool" : "/v1/connections/deny_tool";
    post(path, { connection: item.id, tool: tool.name })
      .then(() => {
        setAsking(null);
        onChanged();
      })
      .catch((reason: unknown) => setError(reason))
      .finally(() => setBusy(null));
  };

  return (
    <details className="mcp-tools">
      <summary>
        {words.toolsTitle} · {words.toolsSummary(tools.filter((t) => t.permission === "allowed" && !t.gone).length, tools.filter((t) => !t.gone).length)}
      </summary>
      <p className="quiet small">{words.untrusted}</p>
      <ul className="plain mcp-tool-list">
        {tools.map((tool) => {
          const on = tool.permission === "allowed";
          return (
            <li key={tool.name} className={tool.gone ? "mcp-tool gone" : "mcp-tool"}>
              <div className="mcp-tool-main">
                <p className="mcp-tool-name">
                  <code>{tool.name}</code>
                  <Pill tone={tool.classification === "read" ? "neutral" : "warning"} dot={false}>
                    {tool.classification === "read" ? words.reads : words.changes}
                  </Pill>
                  {tool.gone ? <span className="quiet small">{words.gone}</span> : null}
                </p>
                {tool.description ? <p className="quiet small mcp-tool-description">{tool.description}</p> : null}
              </div>
              {item.yours && !tool.gone ? (
                <button
                  type="button"
                  role="switch"
                  className="switch"
                  aria-checked={on}
                  aria-label={words.allow(tool.name)}
                  disabled={busy === tool.name}
                  onClick={() => {
                    if (on) set(tool, false);
                    else if (tool.classification === "read") set(tool, true);
                    else setAsking(tool);
                  }}
                >
                  <span className="switch-track" aria-hidden="true">
                    <span className="switch-thumb" />
                  </span>
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
      <ErrorNote error={error} />
      {asking ? (
        <Modal title={words.allowTitle(asking.name)} testId="allow-tool" onClose={() => setAsking(null)}>
          <p>{words.allowWrite(asking.name, item.name)}</p>
          {asking.description ? <p className="quiet small">{asking.description}</p> : null}
          <div className="modal-actions">
            <button type="button" className="button" onClick={() => setAsking(null)} autoFocus>
              {words.keepDenied}
            </button>
            <button type="button" className="button primary" disabled={busy !== null} onClick={() => set(asking, true)}>
              {words.allowYes}
            </button>
          </div>
        </Modal>
      ) : null}
    </details>
  );
}
