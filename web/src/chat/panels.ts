/** The panels that open beside the chat. */
export type PanelId = "connections" | "files" | "feed" | "search" | "budget" | "models" | "settings" | "runs" | "memory" | "board" | "plan" | "thread";

export interface PanelState {
  id: PanelId;
  file?: string;
  runId?: string;
  threadId?: number;
}

export const PANEL_ORDER: Exclude<PanelId, "thread">[] = [
  "connections",
  "files",
  "feed",
  "search",
  "budget",
  "models",
  "settings",
  "runs",
  "memory",
  "board",
  "plan",
];
