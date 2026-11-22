/** The project a decision card in the chat belongs to, and how it hears about and reports changes. */
import { createContext } from "react";

export interface ItemsScope {
  projectId: string;
  /** Changes whenever the live stream reports a change in the project, so open cards reload. */
  changes: number;
  /** Tells the page a decision was made, so the header and panels reload. */
  onChanged(): void;
}

export const ItemsContext = createContext<ItemsScope | null>(null);
