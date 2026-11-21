/** The panels that open beside the chat. */
export type PanelId = "files" | "feed" | "search" | "budget" | "models" | "settings" | "runs" | "thread";

export interface PanelState {
  id: PanelId;
  file?: string;
  runId?: string;
  threadId?: number;
}

export const PANEL_ORDER: Exclude<PanelId, "thread">[] = [
  "files",
  "feed",
  "search",
  "budget",
  "models",
  "settings",
  "runs",
];
