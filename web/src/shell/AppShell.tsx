/**
 * The app shell. Two primary places, Home (what needs me) and Projects, plus Settings; everything
 * else is one level down or in the ⌘K palette (docs/design/ia-map.md). On a desktop the places sit
 * in a sidebar with the person's projects; on a phone they sit in a bottom tab bar under one thumb.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { FolderKanban, Home, Keyboard, Plus, Search, Settings } from "lucide-react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { CommandPalette, type PaletteItem } from "../components/CommandPalette";
import { useThemeContext } from "../components/ThemeButton";
import { useNeedsYou } from "../needs/NeedsYou";
import { t } from "../strings";
import { projectLayout, shell } from "../strings.shell";
import { Logo } from "../ui/Logo";
import { usePalette } from "./palette";
import { sortProjects, useProjects } from "./projects";
import { Shortcuts } from "./Shortcuts";
import { isTyping, useGoShortcuts } from "./useKeySequence";
import { UserMenu } from "./UserMenu";

function Count({ value, label }: { value: number; label: string }): JSX.Element | null {
  if (value === 0) return null;
  return (
    <span className="count" data-testid="nav-needs-count">
      <span aria-hidden="true">{value}</span>
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function AppShell({ children }: { children: ReactNode }): JSX.Element {
  const needs = useNeedsYou();
  const projects = useProjects();
  const { person, signOut } = useAuth();
  const { setPreference } = useThemeContext();
  const palette = usePalette();
  const navigate = useNavigate();
  const location = useLocation();
  const list = useMemo(() => sortProjects(projects.data?.items ?? []), [projects.data]);

  // Projects created elsewhere (the Founder, a form) appear in the sidebar without a reload.
  const { reload } = projects;
  useEffect(() => {
    reload();
  }, [location.pathname, reload]);

  // Ctrl/Cmd+K opens the command palette from anywhere; "?" lists the shortcuts.
  const { setOpen } = palette;
  const [keysOpen, setKeysOpen] = useState(false);
  useGoShortcuts({ h: () => navigate("/"), p: () => navigate("/projects"), s: () => navigate("/settings") });
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      } else if (event.key === "?" && !isTyping(event.target) && !document.querySelector("dialog[open]")) {
        event.preventDefault();
        setKeysOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  const items = useMemo<PaletteItem[]>(() => {
    const go = shell.palette.go;
    const base: PaletteItem[] = [
      { key: "go-home", label: shell.nav.home, detail: go, icon: <Home size={16} />, keywords: "inbox desk needs decisions", run: () => navigate("/") },
      { key: "go-projects", label: shell.nav.projects, detail: go, icon: <FolderKanban size={16} />, keywords: "all projects", run: () => navigate("/projects") },
      { key: "go-settings", label: shell.nav.settings, detail: go, icon: <Settings size={16} />, keywords: "models keys people admin", run: () => navigate("/settings") },
      { key: "new", label: shell.nav.newProject, detail: shell.palette.act, icon: <Plus size={16} />, keywords: "start draft founder create", run: () => navigate("/draft") },
      ...list.map((project) => ({
        key: `project-${project.project_id}`,
        label: t.palette.switchTo(project.name),
        detail: projectLayout.states[project.state] ?? project.state,
        group: shell.palette.projects,
        run: () => navigate(`/projects/${project.project_id}`),
      })),
      { key: "theme-system", label: shell.user.system, detail: shell.palette.appearance, keywords: "theme light dark", run: () => setPreference("system") },
      { key: "theme-light", label: `${shell.user.light} ${shell.user.theme.toLowerCase()}`, detail: shell.palette.appearance, keywords: "light and dark", run: () => setPreference("light") },
      { key: "theme-dark", label: `${shell.user.dark} ${shell.user.theme.toLowerCase()}`, detail: shell.palette.appearance, keywords: "light and dark", run: () => setPreference("dark") },
      { key: "keys", label: shell.keys.open, detail: shell.palette.act, icon: <Keyboard size={16} />, keywords: "help keyboard", run: () => setKeysOpen(true) },
      { key: "signout", label: t.app.signOut, detail: shell.palette.act, run: () => void signOut() },
    ];
    return [...palette.pageItems, ...base];
  }, [list, navigate, palette.pageItems, setPreference, signOut]);

  const needsLabel = shell.nav.needsLabel(needs.count);
  const shortcut = isMac ? "⌘K" : "Ctrl K";

  return (
    <div className={location.pathname.startsWith("/projects/") ? "shell in-project" : "shell"}>
      <a href="#content" className="skip-link">
        {shell.skip}
      </a>
      <aside className="sidebar" aria-label={shell.nav.label}>
        <Link to="/" className="brand sidebar-brand">
          <Logo size={26} />
        </Link>
        <button type="button" className="sidebar-search" onClick={() => setOpen(true)} aria-keyshortcuts="Control+K Meta+K">
          <Search size={16} aria-hidden="true" />
          <span>{shell.nav.search}</span>
          <kbd aria-hidden="true">{shortcut}</kbd>
        </button>
        <nav aria-label={shell.nav.label} className="sidebar-nav">
          <NavLink to="/" end className="nav-item" data-testid="nav-home">
            <Home size={18} aria-hidden="true" />
            <span>{shell.nav.home}</span>
            <Count value={needs.count} label={needsLabel} />
          </NavLink>
          <NavLink to="/projects" end className="nav-item">
            <FolderKanban size={18} aria-hidden="true" />
            <span>{shell.nav.projects}</span>
          </NavLink>
          <NavLink to="/settings" className="nav-item">
            <Settings size={18} aria-hidden="true" />
            <span>{shell.nav.settings}</span>
          </NavLink>
        </nav>
        <div className="sidebar-section">
          <div className="sidebar-heading">
            <span className="eyebrow">{shell.nav.yourProjects}</span>
            <Link to="/draft" className="button ghost small icon-only" aria-label={shell.nav.newProject} title={shell.nav.newProject}>
              <Plus size={16} aria-hidden="true" />
            </Link>
          </div>
          {list.length === 0 && projects.data ? <p className="quiet sidebar-empty">{shell.nav.noProjects}</p> : null}
          <ul className="plain sidebar-projects">
            {list.map((project) => {
              const count = needs.countFor(project.project_id);
              return (
                <li key={project.project_id}>
                  <NavLink to={`/projects/${project.project_id}`} className="nav-item project-item">
                    <span className={`project-dot state-${project.state}`} aria-hidden="true" />
                    <span className="project-item-name">{project.name}</span>
                    <span className="visually-hidden">, {projectLayout.states[project.state] ?? project.state}</span>
                    <Count value={count} label={shell.nav.needsLabel(count)} />
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
        <div className="sidebar-foot">
          <UserMenu placement="above" />
        </div>
      </aside>

      <header className="topbar">
        <Link to="/" className="brand" aria-label={`${t.app.name}, ${shell.nav.home}`}>
          <Logo size={24} />
        </Link>
        <span className="spacer" />
        <button type="button" className="button ghost icon-only" onClick={() => setOpen(true)} aria-label={shell.nav.searchHint}>
          <Search size={20} aria-hidden="true" />
        </button>
        <UserMenu compact placement="below" />
      </header>

      <div className="shell-main" id="content" tabIndex={-1}>
        {children}
      </div>

      <nav className="tabbar" aria-label={shell.nav.label}>
        <NavLink to="/" end className="tab-item">
          <span className="tab-icon">
            <Home size={22} aria-hidden="true" />
            {needs.count > 0 ? (
              <span className="tab-badge" aria-hidden="true">
                {needs.count}
              </span>
            ) : null}
          </span>
          <span>{shell.nav.home}</span>
          <span className="visually-hidden">, {needsLabel}</span>
        </NavLink>
        <NavLink to="/projects" className="tab-item">
          <span className="tab-icon">
            <FolderKanban size={22} aria-hidden="true" />
          </span>
          <span>{shell.nav.projects}</span>
        </NavLink>
        <NavLink to="/draft" end className="tab-item">
          <span className="tab-icon">
            <Plus size={22} aria-hidden="true" />
          </span>
          <span>{shell.nav.newProject.split(" ")[0]}</span>
        </NavLink>
        <NavLink to="/settings" className="tab-item">
          <span className="tab-icon">
            <Settings size={22} aria-hidden="true" />
          </span>
          <span>{shell.nav.settings}</span>
        </NavLink>
      </nav>

      {palette.open && person ? <CommandPalette items={items} onClose={() => setOpen(false)} /> : null}
      {keysOpen ? <Shortcuts onClose={() => setKeysOpen(false)} /> : null}
    </div>
  );
}
