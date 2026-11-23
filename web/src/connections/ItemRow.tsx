/**
 * One connection in a list (CON-15): its kind, name, what it is for, how it is used, its health
 * and where it is used. Actions for the owner: replace a secret's value, delete. A secret's value
 * is never shown.
 */
import { useState, type ReactNode } from "react";
import { Braces, KeyRound, LogIn, MoreHorizontal, Plug, RefreshCw, Trash2 } from "lucide-react";
import { post } from "../api/client";
import { ErrorNote } from "../components/common";
import type { Schemas } from "../api/client";
import { fromNow } from "../lib/humanize";
import { connectionWords as words, kindWord } from "../strings.connections";
import { Menu, type MenuItem } from "../ui/Menu";
import { Pill } from "../ui/Status";
import { DeleteDialog } from "./DeleteDialog";
import { healthOf, usageLine } from "./health";
import { McpTools } from "./McpTools";
import { ReplaceDialog } from "./ReplaceDialog";

type Item = Schemas["ConnectionView"];

interface Props {
  item: Item;
  /** Extra controls or lines for the place it is shown in (grants in a project, Attach). */
  children?: ReactNode;
  actions?: ReactNode;
  extraMenu?: MenuItem[];
  onChanged(): void;
}

export function ItemRow({ item, children, actions, extraMenu = [], onChanged }: Props): JSX.Element {
  const [replacing, setReplacing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const health = healthOf(item);
  const menu: MenuItem[] = [...extraMenu];
  if (item.yours && item.kind === "secret") {
    menu.push({ key: "replace", label: words.replace, icon: <RefreshCw size={16} />, run: () => setReplacing(true) });
  }
  if (item.kind === "mcp_server") {
    menu.push({
      key: "test",
      label: words.mcp.testAgain,
      icon: <RefreshCw size={16} />,
      run: () => {
        setError(null);
        post("/v1/connections/test_mcp", { connection: item.id }).then(onChanged).catch(setError);
      },
    });
  }
  if (item.yours && item.mcp?.auth_kind === "oauth") {
    menu.push({
      key: "sign-in",
      label: words.mcp.signIn,
      icon: <LogIn size={16} />,
      run: () => {
        setError(null);
        post("/v1/connections/sign_in", { connection: item.id })
          .then((started) => window.location.assign(started.authorize_url))
          .catch(setError);
      },
    });
  }
  if (item.yours) {
    menu.push({ key: "delete", label: words.delete, icon: <Trash2 size={16} />, danger: true, run: () => setDeleting(true) });
  }
  const meta = [
    usageLine(item),
    words.usedIn(item.used_in),
    item.last_used_at ? words.lastUsed(fromNow(item.last_used_at)) : null,
  ].filter(Boolean);
  return (
    <li className="connection-row" data-testid="connection">
      <span className={`connection-icon kind-${item.kind}`} aria-hidden="true">
        {item.kind === "variable" ? <Braces size={18} /> : item.kind === "mcp_server" ? <Plug size={18} /> : <KeyRound size={18} />}
      </span>
      <div className="connection-main">
        <p className="connection-name">
          <span>{item.name}</span>
          <span className="visually-hidden">, {kindWord(item.kind)}</span>
          <Pill tone={health.tone}>{health.label}</Pill>
        </p>
        <p className="connection-description">{item.description}</p>
        <p className="quiet small">{meta.join(" · ")}</p>
        {item.kind === "variable" && item.value ? <code className="connection-value">{item.value}</code> : null}
        {item.mcp?.last_error && item.mcp.state !== "active" ? (
          <p className="small connection-problem">{words.mcp.lastError(item.mcp.last_error)}</p>
        ) : null}
        {item.mcp?.state === "needs sign-in" && item.yours ? (
          <div>
            <button
              type="button"
              className="button small primary"
              onClick={() => {
                setError(null);
                post("/v1/connections/sign_in", { connection: item.id })
                  .then((started) => window.location.assign(started.authorize_url))
                  .catch(setError);
              }}
            >
              <LogIn size={16} aria-hidden="true" />
              {words.mcp.signIn}
              <span className="visually-hidden"> {item.name}</span>
            </button>
          </div>
        ) : null}
        {item.kind === "mcp_server" ? <McpTools item={item} onChanged={onChanged} /> : null}
        <ErrorNote error={error} />
        {children}
      </div>
      <div className="connection-actions">
        {actions}
        {menu.length > 0 ? (
          <Menu
            label={words.actions(item.name)}
            button={<MoreHorizontal size={16} aria-hidden="true" />}
            className="button small ghost icon-only"
            items={menu}
          />
        ) : null}
      </div>
      {replacing ? (
        <ReplaceDialog
          item={item}
          onClose={() => setReplacing(false)}
          onDone={() => {
            setReplacing(false);
            onChanged();
          }}
        />
      ) : null}
      {deleting ? (
        <DeleteDialog
          item={item}
          onClose={() => setDeleting(false)}
          onDone={() => {
            setDeleting(false);
            onChanged();
          }}
        />
      ) : null}
    </li>
  );
}
