/**
 * A project (CHAT-1, CHAT-18): the conversation with the crew, and beside it the project's places.
 * Tabs: Chat (default), Overview, Work (plan and board), Crew, Deliverables. Every other tool
 * (activity, budget, runs, memory, models, settings, search) opens as a wide docked panel from
 * "More" or the ⌘K palette. The header line answers "what needs me, who is working, what does it
 * cost" from the same data as everywhere else.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { get, post, type Message, type Schemas } from "../api/client";
import { useAuth } from "../auth";
import { Composer, type ComposerHandle } from "../chat/Composer";
import { ListeningDialogs } from "../chat/ListeningDialogs";
import type { MessageHandlers } from "../chat/MessageItem";
import { MessageList } from "../chat/MessageList";
import { PANEL_ORDER, type PanelId, type PanelState } from "../chat/panels";
import { lastMessageId } from "../chat/state";
import { useListening } from "../chat/useListening";
import { useProjectChat } from "../chat/useProjectChat";
import { useUploads } from "../chat/useUploads";
import type { PaletteItem } from "../components/CommandPalette";
import { ErrorNote } from "../components/common";
import { CrewAssembled, markAssembled, shouldShowAssembled } from "../crew/CrewAssembled";
import { CrewView } from "../crew/CrewView";
import { AgentNamesProvider, mentionOf, roleLabel } from "../crew/names";
import { Deliverables } from "../deliverables/Deliverables";
import { AwayNote } from "../desk/AwayNote";
import { ItemsContext, type ItemsScope } from "../desk/context";
import type { MentionTarget } from "../lib/autocomplete";
import { useLoad } from "../lib/useLoad";
import { useNeedsYou, usePageTitle } from "../needs/NeedsYou";
import { ProjectOverview } from "../overview/ProjectOverview";
import { ProjectPanel } from "../panels/ProjectPanel";
import { ChatRail } from "../project/ChatRail";
import { NeedsSheet } from "../project/NeedsSheet";
import { NeedsStack } from "../project/NeedsStack";
import { ProjectTop, TAB_ORDER, type ProjectTab } from "../project/ProjectTop";
import { StartDialog } from "../project/StartDialog";
import { WorkView } from "../project/WorkView";
import { usePaletteItems } from "../shell/palette";
import { useGoShortcuts } from "../shell/useKeySequence";
import { t } from "../strings";
import { Skeleton } from "../ui/Skeleton";
import { projectLayout, shell } from "../strings.shell";

function tabOf(value: string | undefined): ProjectTab {
  return TAB_ORDER.includes(value as ProjectTab) ? (value as ProjectTab) : "chat";
}

export function Project(): JSX.Element {
  const params = useParams();
  const projectId = params.projectId ?? "";
  const tab = tabOf(params.tab);
  const navigate = useNavigate();
  const { state, actions } = useProjectChat(projectId);
  const listening = useListening(projectId, state, actions);
  const needs = useNeedsYou();
  const [panel, setPanel] = useState<PanelState | null>(null);
  const [needsOpen, setNeedsOpen] = useState(false);
  const [startWaiting, setStartWaiting] = useState<Schemas["BlockerItem"][] | null>(null);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [dragging, setDragging] = useState(false);
  const [pendingInsert, setPendingInsert] = useState<string | null>(null);
  const [fileToOpen, setFileToOpen] = useState<string | undefined>(undefined);
  const [search, setSearch] = useSearchParams();
  const [assembling, setAssembling] = useState(false);
  const composer = useRef<ComposerHandle>(null);

  const status = useLoad(() => get("/v1/projects/status", { project_id: projectId }), [projectId, state.header?.state]);
  const help = useLoad(() => get("/v1/chat/help"), []);
  const roster = useLoad(() => get("/v1/roster/show", { project_id: projectId }), [projectId, state.changes]);
  const decisionItems = useLoad(() => get("/v1/items/list", { project_id: projectId, open_only: false }), [projectId, state.changes]);
  const known = useMemo(() => new Map((decisionItems.data?.items ?? []).map((entry) => [entry.id, entry])), [decisionItems.data]);
  const uploads = useUploads(projectId, actions.refresh);

  const projectName = status.data?.name ?? t.project.fallbackName;

  // The crew assembles once: right after the Founder starts the project, or the first time the
  // person opens the Crew tab once a team exists. Never in the middle of other work.
  const justHired = search.get("crew") === "hired";
  const seats = roster.data?.seats ?? [];
  const teams = roster.data?.teams.length ?? 0;
  useEffect(() => {
    if (!roster.data || assembling || seats.length === 0) return;
    if (justHired || (tab === "crew" && teams > 0 && shouldShowAssembled(projectId))) setAssembling(true);
  }, [roster.data, justHired, tab, teams, projectId, assembling, seats.length]);
  const doneAssembling = useCallback(() => {
    markAssembled(projectId);
    setAssembling(false);
    if (search.has("crew")) {
      search.delete("crew");
      setSearch(search, { replace: true });
    }
  }, [projectId, search, setSearch]);
  usePageTitle(projectName);

  // A change in the project may add to or clear what waits on the person: ask the desk again.
  const { reload: reloadNeeds } = needs;
  useEffect(() => {
    if (state.changes > 0) reloadNeeds();
  }, [state.changes, reloadNeeds]);

  const goTab = useCallback(
    (next: ProjectTab) => navigate(next === "chat" ? `/projects/${projectId}` : `/projects/${projectId}/${next}`),
    [navigate, projectId],
  );

  useGoShortcuts({
    c: () => goTab("chat"),
    o: () => goTab("overview"),
    w: () => goTab("work"),
    r: () => goTab("crew"),
    d: () => goTab("deliverables"),
  });

  const open = useCallback((id: PanelId) => setPanel({ id }), []);
  // A link may name a panel to open (`?panel=connections`, where an MCP sign-in returns).
  useEffect(() => {
    const wanted = search.get("panel");
    if (wanted && (PANEL_ORDER as string[]).includes(wanted)) {
      setPanel({ id: wanted as PanelId });
      search.delete("panel");
      setSearch(search, { replace: true });
    }
  }, [search, setSearch]);
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

  // Text queued for the message box while another tab was shown ("Message CEO" from the Crew).
  useEffect(() => {
    if (tab === "chat" && pendingInsert !== null) {
      composer.current?.insert(pendingInsert);
      composer.current?.focus();
      setPendingInsert(null);
    }
  }, [tab, pendingInsert]);

  const jump = useCallback(
    (messageId: number) => {
      if (window.matchMedia("(max-width: 1099px)").matches) setPanel(null);
      if (tab !== "chat") goTab("chat");
      requestAnimationFrame(() => {
        const element = document.getElementById(`message-${messageId}`);
        const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        element?.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" });
        element?.focus({ preventScroll: true });
      });
    },
    [goTab, tab],
  );

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

  // Tell the server how far this person has read, while the page is in view.
  const marked = useRef(0);
  const newest = lastMessageId(state.messages);
  useEffect(() => {
    if (tab !== "chat" || newest <= marked.current || document.visibilityState !== "visible") return;
    marked.current = newest;
    post("/v1/chat/mark_read", { project_id: projectId, message_id: newest }).catch(() => undefined);
  }, [newest, projectId, tab]);

  const mentions = useMemo<MentionTarget[]>(
    () => [
      ...(roster.data?.seats ?? [])
        .filter((seat) => seat.state !== "stood down")
        .map((seat) => ({
          name: mentionOf(seat.display_name || seat.name),
          detail: t.composer.seatDetail(roleLabel(seat)),
          aliases: [seat.name],
        })),
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
      ...TAB_ORDER.map((id) => ({
        key: `tab-${id}`,
        label: projectLayout.tabs[id],
        detail: projectName,
        group: shell.palette.project,
        keywords: id === "work" ? "plan board tasks requirements" : id === "deliverables" ? "files outputs" : id === "crew" ? "agents team org" : "",
        run: () => goTab(id),
      })),
      ...PANEL_ORDER.map((id) => ({
        key: `panel-${id}`,
        label: t.palette.openPanel(t.panels.names[id]),
        detail: t.palette.panel,
        group: shell.palette.project,
        run: () => open(id),
      })),
      ...Object.entries(commands).map(([name, detail]) => ({
        key: `command-${name}`,
        label: name,
        detail,
        group: shell.palette.commands,
        run: () => {
          if (tab !== "chat") goTab("chat");
          setPendingInsert(`${name} `);
        },
      })),
    ],
    [commands, goTab, open, projectName, tab],
  );
  usePaletteItems(paletteItems);

  const items = useMemo<ItemsScope>(
    () => ({
      projectId,
      changes: state.changes,
      onChanged: () => {
        actions.refresh();
        reloadNeeds();
      },
      known,
    }),
    [projectId, state.changes, actions, reloadNeeds, known],
  );

  const send = (body: string): void => {
    void actions.send(body, replyTo?.id ?? null);
    setReplyTo(null);
  };

  const mine = needs.forProject(projectId);

  let view: JSX.Element;
  switch (tab) {
    case "overview":
      view = (
        <ProjectOverview
          projectId={projectId}
          changes={state.changes}
          header={state.header}
          onTab={goTab}
          onPanel={(id) => open(id)}
          onOpenFile={(name) => {
            setFileToOpen(name);
            goTab("deliverables");
          }}
        />
      );
      break;
    case "work":
      view = <WorkView projectId={projectId} changes={state.changes} onChanged={items.onChanged} />;
      break;
    case "crew":
      view = (
        <CrewView
          projectId={projectId}
          changes={state.changes}
          header={state.header}
          canRename={status.data?.your_role === "chairman" || status.data?.your_role === "co-chair"}
          onMessage={(mention) => {
            setPendingInsert(`@${mention} `);
            goTab("chat");
          }}
          onOpenRun={(runId) => setPanel({ id: "runs", runId })}
          onRenamed={roster.reload}
        />
      );
      break;
    case "deliverables":
      view = <Deliverables projectId={projectId} changes={state.changes} initialFile={fileToOpen} />;
      break;
    default:
      view = (
        <>
          <section
            className={dragging ? "chat chat-main is-dragging" : "chat chat-main"}
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
            {state.loaded && state.dropped && !state.live ? (
              <p className="offline" role="status">
                {t.chat.reconnecting}
              </p>
            ) : null}
            <AwayNote projectId={projectId} />
            {needs.loaded && mine.length > 0 ? (
              <NeedsStack projectId={projectId} entries={mine} onChanged={items.onChanged} onOpenAll={() => setNeedsOpen(true)} />
            ) : null}
            {(!needs.loaded && !needs.error) || (decisionItems.data === undefined && !decisionItems.error) ? (
              <div className="chat-loading">
                <Skeleton lines={4} block />
              </div>
            ) : (
            <MessageList
              state={state}
              handlers={handlers}
              onRetry={actions.retry}
              onDismissPending={actions.dismissPending}
              onDismissNotice={actions.dismissNotice}
              onInterrupt={() => void actions.interrupt()}
              onEarlier={actions.loadEarlier}
            />
            )}
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
          </section>
          <ChatRail
            projectId={projectId}
            changes={state.changes}
            header={state.header}
            needs={[]}
            onNeeds={() => setNeedsOpen(true)}
            onTab={goTab}
            onPanel={open}
          />
        </>
      );
  }

  return (
    <AgentNamesProvider seats={roster.data?.seats}>
    <ItemsContext.Provider value={items}>
      <main className={panel ? "project-shell has-panel" : "project-shell"} aria-labelledby="project-title">
        <ProjectTop
          projectId={projectId}
          name={projectName}
          header={state.header}
          tab={tab}
          needs={mine.length}
          onTab={goTab}
          onPanel={open}
          onNeeds={() => setNeedsOpen(true)}
          onAction={(action) => {
            if (action !== "start") {
              void actions.projectAction(action);
              return;
            }
            // CON-5: show what would hold agents before starting, rather than a refusal after.
            void get("/v1/projects/readiness", { project_id: projectId })
              .then((found) => (found.ready ? actions.projectAction("start") : setStartWaiting(found.waiting)))
              .catch(actions.reportError);
          }}
        />
        <ErrorNote error={status.error} />
        {startWaiting ? (
          <StartDialog
            waiting={startWaiting}
            onClose={() => setStartWaiting(null)}
            onAddNow={() => {
              setStartWaiting(null);
              open("connections");
            }}
            onStartWithout={async () => {
              await actions.projectAction("start", { withoutMissing: true });
              setStartWaiting(null);
            }}
            onMarkDone={async (need) => {
              try {
                await post("/v1/connections/mark_need_done", { project_id: projectId, need: need.name, kind: need.kind });
                const found = await get("/v1/projects/readiness", { project_id: projectId });
                if (found.ready) {
                  setStartWaiting(null);
                  await actions.projectAction("start");
                } else {
                  setStartWaiting(found.waiting);
                }
              } catch (reason: unknown) {
                actions.reportError(reason);
              }
            }}
          />
        ) : null}
        <div className="project-body">
          <div className={tab === "chat" ? "project-view chat-view" : "project-view"} data-testid={`view-${tab}`}>
            {view}
          </div>
          {panel ? (
            <ProjectPanel
              projectId={projectId}
              panel={panel}
              state={state}
              handlers={handlers}
              onClose={closePanel}
              onPanel={setPanel}
              onChanged={items.onChanged}
            />
          ) : null}
        </div>
        <ListeningDialogs listening={listening} />
        {assembling ? (
          <CrewAssembled
            projectId={projectId}
            seats={seats.map((seat) => ({ name: seat.name, displayName: seat.display_name, role: roleLabel(seat), kind: seat.kind }))}
            onDone={() => {
              doneAssembling();
              goTab("crew");
            }}
            onSkip={doneAssembling}
          />
        ) : null}
        {needsOpen ? <NeedsSheet projectName={projectName} entries={mine} onClose={() => setNeedsOpen(false)} onChanged={items.onChanged} /> : null}
      </main>
    </ItemsContext.Provider>
    </AgentNamesProvider>
  );
}
