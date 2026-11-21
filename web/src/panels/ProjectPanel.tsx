/** Picks the panel to show beside the chat. */
import type { MessageHandlers } from "../chat/MessageItem";
import type { PanelState } from "../chat/panels";
import { lastMessageId, type ChatState } from "../chat/state";
import { t } from "../strings";
import { FilesPanel } from "./FilesPanel";
import { PanelFrame } from "./PanelFrame";
import { RunsPanel } from "./RunsPanel";
import { SearchPanel } from "./SearchPanel";
import { SettingsPanel } from "./SettingsPanel";
import { BudgetPanel, FeedPanel, ModelsPanel } from "./SimplePanels";
import { ThreadPanel } from "./ThreadPanel";

interface Props {
  projectId: string;
  panel: PanelState;
  state: ChatState;
  handlers: MessageHandlers;
  onClose(): void;
  onPanel(panel: PanelState): void;
}

export function ProjectPanel({ projectId, panel, state, handlers, onClose, onPanel }: Props): JSX.Element {
  const changes = state.changes;
  let body: JSX.Element;
  switch (panel.id) {
    case "files":
      body = (
        <FilesPanel
          projectId={projectId}
          changes={changes}
          file={panel.file}
          onFile={(file) => onPanel({ id: "files", file })}
        />
      );
      break;
    case "feed":
      body = <FeedPanel projectId={projectId} changes={changes} />;
      break;
    case "search":
      body = (
        <SearchPanel projectId={projectId} onJump={handlers.onJump} onFile={(file) => onPanel({ id: "files", file })} />
      );
      break;
    case "budget":
      body = <BudgetPanel projectId={projectId} changes={changes} />;
      break;
    case "models":
      body = <ModelsPanel projectId={projectId} changes={changes} />;
      break;
    case "settings":
      body = <SettingsPanel projectId={projectId} changes={changes} />;
      break;
    case "runs":
      body = (
        <RunsPanel
          projectId={projectId}
          changes={changes}
          runId={panel.runId}
          onSelect={(runId) => onPanel({ id: "runs", runId })}
        />
      );
      break;
    case "thread":
      body = (
        <ThreadPanel
          projectId={projectId}
          threadId={panel.threadId ?? 0}
          latest={lastMessageId(state.messages)}
          cards={state.cards}
          handlers={handlers}
        />
      );
      break;
  }
  return (
    <PanelFrame title={t.panels.names[panel.id]} onClose={onClose}>
      {body}
    </PanelFrame>
  );
}
