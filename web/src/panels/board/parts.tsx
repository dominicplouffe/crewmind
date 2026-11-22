/** Pieces the Board tabs share: the check label, a state tag, the refresh bar, agent-written text. */
import type { ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import { t } from "../../strings";
import { Pill, type Tone } from "../../ui/Status";
import { slug } from "./logic";

export interface BoardTabProps {
  projectId: string;
  /** Changes whenever the live stream reports a change in the project, so the tab reloads. */
  changes: number;
}

/** How strongly a check label vouches for the work, for its dot only. The words are the server's. */
function checkTone(label: string): Tone {
  if (label === "verified") return "success";
  if (label === "reviewed") return "accent";
  if (label === "failed" || label === "rejected") return "danger";
  return "neutral";
}

/** The server's check label, word for word. Only its style differs per label: no ticks, no other words. */
export function CheckLabel({ label }: { label: string }): JSX.Element {
  return (
    <span className={`check check-${slug(label)}`} data-testid="check-label">
      <Pill tone={checkTone(label)}>
        <span className="visually-hidden">{t.board.tasks.labelOf}: </span>
        {label}
      </Pill>
    </span>
  );
}

function taskTone(state: string): Tone {
  if (state === "done" || state === "finished" || state === "closed") return "success";
  if (state === "in progress" || state === "claimed" || state === "running") return "accent";
  if (state === "blocked" || state === "failed") return "danger";
  if (state === "ready") return "info";
  return "neutral";
}

export function StateTag({ state }: { state: string }): JSX.Element {
  return (
    <span className="state-tag" data-testid="state-tag">
      <Pill tone={taskTone(state)}>
        <span className="visually-hidden">{t.board.tasks.stateOf}: </span>
        <span className="cap">{state}</span>
      </Pill>
    </span>
  );
}

/** A row of controls above a list, with the refresh button at its end. */
export function Bar({ onRefresh, busy, children }: { onRefresh(): void; busy: boolean; children?: ReactNode }): JSX.Element {
  return (
    <div className="row wrap board-bar">
      {children}
      <span className="spacer" />
      <button type="button" className="button small ghost" onClick={onRefresh} disabled={busy}>
        <RefreshCw size={14} aria-hidden="true" />
        {t.board.refresh}
      </button>
    </div>
  );
}

/** Text an agent wrote, shown as plain text with its line breaks kept. It is never treated as markup. */
export function AgentText({ text, className }: { text: string; className?: string }): JSX.Element {
  return <span className={`agent-text ${className ?? ""}`}>{text}</span>;
}
