/** Reads chat history a page at a time: the newest page first, older pages on request, new messages after an id. */
import { get, type Message } from "../api/client";

/** How many messages one request asks for (display only; the server caps it). */
export const HISTORY_PAGE = 50;

export interface HistoryPage {
  items: Message[];
  /** Pass as `before` to get the page before this one; null when there is none. */
  earlier: number | null;
}

/** The newest page, or the page that ends just before the message `before`. */
export async function loadPage(projectId: string, before?: number): Promise<HistoryPage> {
  const page = await get("/v1/chat/history", { project_id: projectId, limit: HISTORY_PAGE, before });
  return { items: page.items, earlier: page.earlier ?? null };
}

/** Every message stored after the message `after`, oldest first. */
export async function loadAfter(projectId: string, after: number): Promise<Message[]> {
  const items: Message[] = [];
  let cursor = String(after);
  for (;;) {
    const page = await get("/v1/chat/history", { project_id: projectId, limit: HISTORY_PAGE, after: cursor });
    items.push(...page.items);
    if (!page.next) return items;
    cursor = page.next;
  }
}
