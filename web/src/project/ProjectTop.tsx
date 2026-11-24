/**
 * The project header (CHAT-18), designed to be read at a glance: the name and state with the one
 * action that fits it; then what needs you, who is working now, what is next and the budget used.
 * Each part opens where its detail lives. On a phone it collapses into one scrollable line.
 */
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Brain,
  Cpu,
  History,
  Inbox,
  MoreHorizontal,
  Pause,
  Play,
  Search,
  SlidersHorizontal,
  PlugZap,
  Wallet,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { Header } from "../api/client";
import type { PanelId } from "../chat/panels";
import { Markdown } from "../components/common";
import { compactNumber, share } from "../lib/humanize";
import { t } from "../strings";
import { projectLayout, shell } from "../strings.shell";
import { Avatar } from "../ui/Avatar";
import { Menu } from "../ui/Menu";
import { Meter } from "../ui/Progress";
import { Pill } from "../ui/Status";
import { STATE_TONE } from "../home/ProjectCard";

export type ProjectTab = "chat" | "overview" | "work" | "crew" | "deliverables";
export const TAB_ORDER: ProjectTab[] = ["chat", "overview", "work", "crew", "deliverables"];

/** Which button fits which state. The server still decides whether the action is allowed. */
const ACTION_FOR_STATE: Record<string, "start" | "hold" | "resume"> = {
  draft: "start",
  running: "hold",
  held: "resume",
  paused: "resume",
};

const MORE: { id: PanelId; icon: JSX.Element }[] = [
  { id: "connections", icon: <PlugZap size={16} /> },
  { id: "feed", icon: <Activity size={16} /> },
  { id: "search", icon: <Search size={16} /> },
  { id: "budget", icon: <Wallet size={16} /> },
  { id: "runs", icon: <History size={16} /> },
  { id: "memory", icon: <Brain size={16} /> },
  { id: "models", icon: <Cpu size={16} /> },
  { id: "settings", icon: <SlidersHorizontal size={16} /> },
];

interface Props {
  projectId: string;
  name: string;
  header: Header | null;
  tab: ProjectTab;
  needs: number;
  onTab(tab: ProjectTab): void;
  onPanel(panel: PanelId): void;
  onNeeds(): void;
  onAction(action: "start" | "hold" | "resume"): void;
}

function doingText(doing: string): string {
  return doing.charAt(0).toUpperCase() + doing.slice(1);
}

export function ProjectTop({ projectId, name, header, tab, needs, onTab, onPanel, onNeeds, onAction }: Props): JSX.Element {
  const action = header ? ACTION_FOR_STATE[header.state] : undefined;
  const working = header?.now ?? [];
  const over = header ? header.budget_wall > 0 && header.budget_spent >= header.budget_wall : false;
  return (
    <header className="project-top">
      <div className="project-titlebar">
        <Link to="/projects" className="button ghost icon-only project-back" aria-label={shell.nav.projects}>
          <ArrowLeft size={20} aria-hidden="true" />
        </Link>
        <h1 id="project-title">{name}</h1>
        {header ? (
          <span data-testid="project-state" data-state={header.state}>
            <Pill tone={STATE_TONE[header.state] ?? "neutral"} live={header.state === "running" && working.length > 0}>
              {projectLayout.states[header.state] ?? header.state}
            </Pill>
          </span>
        ) : null}
        <span className="title-actions row">
          {action ? (
            <button
              type="button"
              className={action === "start" ? "button primary small" : "button small"}
              onClick={() => onAction(action)}
            >
              {action === "hold" ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
              {t.header.actions[action]}
            </button>
          ) : null}
        </span>
      </div>

      <section className="statusline" aria-label={t.header.label}>
        <button
          type="button"
          className={needs > 0 ? "status-chip needs" : "status-chip"}
          onClick={onNeeds}
          data-testid="waiting-count"
          data-count={needs}
        >
          <Inbox size={14} aria-hidden="true" />
          {projectLayout.needsYou(needs)}
        </button>
        <span className="divider" aria-hidden="true" />
        <button type="button" className="status-chip" onClick={() => onTab("crew")} data-testid="now">
          {working.length > 0 ? (
            <>
              <span className="avatar-stack" aria-hidden="true">
                {working.slice(0, 3).map((work) => (
                  <Avatar key={work.seat} name={work.name || work.seat} hueKey={work.seat} size="xs" status="working" />
                ))}
              </span>
              <span>
                {working.length === 1 && working[0]
                  ? t.header.working(working[0].name || working[0].seat, doingText(working[0].doing))
                  : projectLayout.working(working.length)}
              </span>
            </>
          ) : (
            <span>{t.header.nowEmpty}</span>
          )}
        </button>
        {header && header.next.length > 0 ? (
          <>
            <span className="divider hide-phone" aria-hidden="true" />
            <button type="button" className="status-chip hide-phone" onClick={() => onPanel("feed")}>
              {t.header.next}: {header.next[0]}
            </button>
          </>
        ) : null}
        {header ? (
          <>
            <span className="divider" aria-hidden="true" />
            <button type="button" className="status-chip status-budget" onClick={() => onPanel("budget")}>
              <Meter value={header.budget_spent} max={header.budget_wall} label={header.budget} tone={over ? "danger" : "accent"} />
              <span className="visually-hidden">{t.header.budget}: </span>
              <span className="tabular">
                {compactNumber(header.budget_spent)} / {compactNumber(header.budget_wall)}
                <span className="hide-phone"> tokens · {share(header.budget_spent, header.budget_wall)}</span>
              </span>
            </button>
          </>
        ) : null}
      </section>

      {header && header.holds.length > 0 ? (
        <div className="holdbar" role="status">
          <AlertTriangle size={16} aria-hidden="true" />
          <div>
            <strong>{t.header.holds}</strong>
            <ul>
              {header.holds.map((hold, index) => (
                <li key={index} className="hold">
                  <Markdown source={t.header.hold(hold.reason, hold.lifts)} className="inline" />
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      {header && header.notes.length > 0 ? (
        <ul className="plain project-notes quiet">
          {header.notes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      ) : null}
      {header && header.unread > 0 ? <span className="visually-hidden">{t.header.unread(header.unread)}</span> : null}

      <div className="project-tabbar">
        <nav className="project-tabs" aria-label={shell.nav.tabsLabel}>
          {TAB_ORDER.map((id) => (
            <Link
              key={id}
              to={id === "chat" ? `/projects/${projectId}` : `/projects/${projectId}/${id}`}
              className="project-tab"
              aria-current={tab === id ? "page" : undefined}
            >
              {projectLayout.tabs[id]}
              {id === "chat" && header && header.unread > 0 && tab !== "chat" ? (
                <span className="count" aria-hidden="true">
                  {header.unread}
                </span>
              ) : null}
            </Link>
          ))}
        </nav>
        <Menu
          label={projectLayout.moreLabel}
          className="button ghost small"
          testId="project-more"
          button={
            <>
              <MoreHorizontal size={16} aria-hidden="true" />
              {projectLayout.more}
            </>
          }
          items={MORE.map(({ id, icon }) => ({ key: id, label: t.panels.names[id], icon, run: () => onPanel(id) }))}
        />
      </div>
    </header>
  );
}
