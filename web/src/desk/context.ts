/** The project a decision card in the chat belongs to, and how it hears about and reports changes. */
import { createContext } from "react";
import type { Schemas } from "../api/client";

export interface ItemsScope {
  projectId: string;
  /** Changes whenever the live stream reports a change in the project, so open cards reload. */
  changes: number;
  /** Tells the page a decision was made, so the header and panels reload. */
  onChanged(): void;
  /**
   * The project's decision items as last loaded in one list, so a card in the chat paints complete
   * at once and only then asks for its own fresh copy (no layout shift).
   */
  known?: Map<number, Schemas["ItemView"]>;
}

export const ItemsContext = createContext<ItemsScope | null>(null);
