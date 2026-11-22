/** The project page: the chat, the always-visible header, and the panels beside it. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { get, post, type Message } from "../api/client";
import { useAuth } from "../auth";
import { Composer, type ComposerHandle } from "../chat/Composer";
import { HeaderStrip } from "../chat/HeaderStrip";
import { ListeningDialogs } from "../chat/ListeningDialogs";
import type { MessageHandlers } from "../chat/MessageItem";
import { MessageList } from "../chat/MessageList";
import { PANEL_ORDER, type PanelId, type PanelState } from "../chat/panels";
import { lastMessageId } from "../chat/state";
import { useListening } from "../chat/useListening";
import { useProjectChat } from "../chat/useProjectChat";
import { useUploads } from "../chat/useUploads";
import { AlertsButton } from "../components/AlertsButton";
import { CommandPalette, type PaletteItem } from "../components/CommandPalette";
import { ErrorNote } from "../components/common";
import { ThemeButton, useThemeContext } from "../components/ThemeButton";
import { AwayNote } from "../desk/AwayNote";
import { ItemsContext, type ItemsScope } from "../desk/context";
import { DeskLink } from "../desk/DeskLink";
import type { MentionTarget } from "../lib/autocomplete";
import { useLoad } from "../lib/useLoad";
import { ProjectPanel } from "../panels/ProjectPanel";
import { t } from "../strings";

export function Project(): JSX.Element {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const { signOut } = useAuth();
  const theme = useThemeContext();
  const { state, actions } = useProjectChat(projectId);
  const listening = useListening(projectId, state, actions);
  const [panel, setPanel] = useState<PanelState | null>(null);
  const [palette, setPalette] = useState(false);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [dragging, setDragging] = useState(false);
  const composer = useRef<ComposerHandle>(null);

  const status = useLoad(() => get("/v1/projects/status", { project_id: projectId }), [projectId]);
  const help = useLoad(() => get("/v1/chat/help"), []);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, state.changes]);
  const projects = useLoad(() => get("/v1/projects/list", {}), []);
  const uploads = useUploads(projectId, actions.refresh);

  const projectName = status.data?.name ?? t.project.fallbackName;
  useEffect(() => {
    document.title = t.project.pageTitle(projectName);
    return () => {
      document.title = t.app.name;
    };
  }, [projectName]);

  const open = useCallback((id: PanelId) => setPanel({ id }), []);
  const refocus = useRef(false);
  const closePanel = useCallback(() => {
    refocus.current = true;
    setPanel(null);
  }, []);
  // After a panel closes, focus returns to the message box (once it is visible again on a phone).
  useEffect(() => {
    if (panel === null && refocus.current) {
      refocus.current = false;
      composer.current?.focus();
    }
  }, [panel]);

  const jump = useCallback((messageId: number) => {
    if (window.matchMedia("(max-width: 899px)").matches) setPanel(null);
    requestAnimationFrame(() => {
      const element = document.getElementById(`message-${messageId}`);
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      element?.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" });
      element?.focus({ preventScroll: true });
    });
  }, []);

  const handlers = useMemo<MessageHandlers>(
    () => ({
      onReply: (message) => {
        setReplyTo(message);
        composer.current?.focus();
      },
      onThread: (threadId) => setPanel({ id: "thread", threadId }),
      onJump: jump,
      onPreview: (name) => setPanel({ id: "files", file: name }),
      onTrace: (runId) => setPanel({ id: "runs", runId }),
      onAccept: actions.acceptCard,
      onDismiss: actions.dismissCard,
      ...listening.handlers,
    }),
    [actions, jump, listening.handlers],
  );

  // Ctrl/Cmd+K opens the command palette from anywhere on the page.
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Tell the server how far this person has read, while the page is in view.
  const marked = useRef(0);
  const newest = lastMessageId(state.messages);
  useEffect(() => {
    if (newest <= marked.current || document.visibilityState !== "visible") return;
    marked.current = newest;
    post("/v1/chat/mark_read", { project_id: projectId, message_id: newest }).catch(() => undefined);
  }, [newest, projectId]);

  const mentions = useMemo<MentionTarget[]>(
    () => [
      ...(roster.data?.seats ?? []).map((seat) => ({ name: seat.name, detail: t.composer.seatDetail(seat.role) })),
      ...(roster.data?.teams ?? []).map((team) => ({ name: team, detail: t.composer.teamDetail })),
    ],
    [roster.data],
  );
  const commands = useMemo(() => help.data?.commands ?? {}, [help.data]);
  const myName = useAuth().person?.name;
  const history = useMemo(
    () =>
      state.messages
        .filter((message) => message.author_kind === "person" && message.kind === "message" && message.author === myName)
        .map((message) => message.body),
    [state.messages, myName],
  );

  const paletteItems = useMemo<PaletteItem[]>(
    () => [
      ...PANEL_ORDER.map((id) => ({
        key: `panel-${id}`,
        label: t.palette.openPanel(t.panels.names[id]),
        detail: t.palette.panel,
        run: () => open(id),
      })),
      ...Object.entries(commands).map(([name, detail]) => ({
        key: `command-${name}`,
        label: name,
        detail,
        run: () => composer.current?.insert(`${name} `),
      })),
      ...(projects.data?.items ?? [])
        .filter((project) => project.project_id !== projectId)
        .map((project) => ({
          key: `project-${project.project_id}`,
          label: t.palette.switchTo(project.name),
          detail: t.palette.project,
          run: () => navigate(`/projects/${project.project_id}`),
        })),
      { key: "projects", label: t.palette.allProjects, detail: t.palette.project, run: () => navigate("/") },
      { key: "desk", label: t.decisions.desk.palette, detail: t.palette.project, run: () => navigate("/desk") },
      { key: "theme", label: t.palette.theme, detail: t.palette.setting, run: theme.toggle },
      { key: "signout", label: t.app.signOut, detail: t.palette.setting, run: () => void signOut() },
    ],
    [commands, navigate, open, projectId, projects.data, signOut, theme.toggle],
  );

  const items = useMemo<ItemsScope>(
    () => ({ projectId, changes: state.changes, onChanged: actions.refresh }),
    [projectId, state.changes, actions.refresh],
  );

  const send = (body: string): void => {
    void actions.send(body, replyTo?.id ?? null);
    setReplyTo(null);
  };

  return (
    <ItemsContext.Provider value={items}>
      <div className={panel ? "project has-panel" : "project"}>
        <header className="appbar">
          <Link to="/" className="brand">
            {t.app.name}
          </Link>
          <h1 className="project-title">{projectName}</h1>
          <span className="spacer" />
          <DeskLink changes={state.changes} />
          <nav aria-label={t.panels.navLabel} className="panel-nav">
            {PANEL_ORDER.map((id) => (
              <button
                key={id}
                type="button"
                className="button small"
                aria-pressed={panel?.id === id}
                onClick={() => (panel?.id === id ? closePanel() : open(id))}
              >
                {t.panels.names[id]}
              </button>
            ))}
          </nav>
          <button type="button" className="button small" onClick={() => setPalette(true)} aria-keyshortcuts="Control+K Meta+K">
            {t.palette.open}
          </button>
          <AlertsButton />
          <ThemeButton />
        </header>
        <HeaderStrip header={state.header} onOpen={open} onAction={(action) => void actions.projectAction(action)} />
        <ErrorNote error={status.error} />
        {state.loaded && state.dropped && !state.live ? (
          <p className="offline" role="status">
            {t.chat.reconnecting}
          </p>
        ) : null}
        <div className="workspace">
          <main
            className={dragging ? "chat is-dragging" : "chat"}
            aria-label={t.chat.mainLabel}
            onDragOver={(event) => {
              if (event.dataTransfer.types.includes("Files")) {
                event.preventDefault();
                setDragging(true);
              }
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              if (event.dataTransfer.files.length > 0) {
                event.preventDefault();
                uploads.add(Array.from(event.dataTransfer.files));
              }
              setDragging(false);
            }}
          >
            <AwayNote projectId={projectId} />
            <MessageList
              state={state}
              handlers={handlers}
              onRetry={actions.retry}
              onDismissPending={actions.dismissPending}
              onDismissNotice={actions.dismissNotice}
              onInterrupt={() => void actions.interrupt()}
              onEarlier={actions.loadEarlier}
            />
            {dragging ? <p className="drop-hint">{t.composer.dropHint}</p> : null}
            <Composer
              ref={composer}
              commands={commands}
              mentions={mentions}
              history={history}
              replyTo={replyTo}
              replying={state.typing.length > 0}
              uploads={uploads.uploads}
              onSend={send}
              onCancelReply={() => setReplyTo(null)}
              onInterrupt={() => void actions.interrupt()}
              onFiles={uploads.add}
              onDismissUpload={uploads.dismiss}
            />
          </main>
          {panel ? (
            <ProjectPanel
              projectId={projectId}
              panel={panel}
              state={state}
              handlers={handlers}
              onClose={closePanel}
              onPanel={setPanel}
              onChanged={actions.refresh}
            />
          ) : null}
        </div>
        <ListeningDialogs listening={listening} />
        {palette ? <CommandPalette items={paletteItems} onClose={() => setPalette(false)} /> : null}
      </div>
    </ItemsContext.Provider>
  );
}
