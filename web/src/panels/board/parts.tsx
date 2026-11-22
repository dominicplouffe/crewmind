/** Pieces the Board tabs share: the check label, a state tag, the refresh bar, agent-written text. */
import type { ReactNode } from "react";
import { t } from "../../strings";
import { slug } from "./logic";

export interface BoardTabProps {
  projectId: string;
  /** Changes whenever the live stream reports a change in the project, so the tab reloads. */
  changes: number;
}

/** The server's check label, word for word. Only its quiet style differs per label: no ticks, no other words. */
export function CheckLabel({ label }: { label: string }): JSX.Element {
  return (
    <span className={`marker check check-${slug(label)}`} data-testid="check-label">
      <span className="visually-hidden">{t.board.tasks.labelOf}: </span>
      {label}
    </span>
  );
}

export function StateTag({ state }: { state: string }): JSX.Element {
  return (
    <span className="marker" data-testid="state-tag">
      <span className="visually-hidden">{t.board.tasks.stateOf}: </span>
      {state}
    </span>
  );
}

/** A row of controls above a list, with the refresh button at its end. */
export function Bar({ onRefresh, busy, children }: { onRefresh(): void; busy: boolean; children?: ReactNode }): JSX.Element {
  return (
    <div className="row wrap board-bar">
      {children}
      <span className="spacer" />
      <button type="button" className="button small" onClick={onRefresh} disabled={busy}>
        {t.board.refresh}
      </button>
    </div>
  );
}

/** Text an agent wrote, shown as plain text with its line breaks kept. It is never treated as markup. */
export function AgentText({ text, className }: { text: string; className?: string }): JSX.Element {
  return <span className={`agent-text ${className ?? ""}`}>{text}</span>;
}
