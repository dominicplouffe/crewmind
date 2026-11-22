/** One thread: the message that started it and every reply. */
import { CornerDownRight, MessagesSquare } from "lucide-react";
import { get } from "../api/client";
import { MessageItem, type MessageHandlers } from "../chat/MessageItem";
import type { ChatState } from "../chat/state";
import { ErrorNote } from "../components/common";
import { Empty, Loading } from "./kit";
import { useLoad } from "../lib/useLoad";
import { t } from "../strings";

interface Props {
  projectId: string;
  threadId: number;
  /** The newest stored message id: the thread reloads when it moves. */
  latest: number;
  cards: ChatState["cards"];
  handlers: MessageHandlers;
}

export function ThreadPanel({ projectId, threadId, latest, cards, handlers }: Props): JSX.Element {
  const thread = useLoad(
    () => get("/v1/chat/history", { project_id: projectId, thread_id: threadId, limit: 200 }),
    [projectId, threadId, latest],
  );
  const items = thread.data?.items ?? [];
  return (
    <div data-testid="thread" className="thread">
      <ErrorNote error={thread.error} />
      {thread.loading && !thread.data ? <Loading /> : null}
      {thread.data && items.length === 0 ? <Empty icon={MessagesSquare} title={t.thread.emptyTitle} next={t.thread.emptyNext} /> : null}
      {items.map((message) => {
        const cardId = (message.detail as { card?: unknown } | null)?.card;
        return (
          <MessageItem
            key={message.id}
            message={message}
            parent={undefined}
            card={typeof cardId === "number" ? cards[cardId] : undefined}
            replies={0}
            handlers={handlers}
            compact
          />
        );
      })}
      <button type="button" className="button small ghost thread-jump" onClick={() => handlers.onJump(threadId)}>
        <CornerDownRight size={14} aria-hidden="true" />
        {t.thread.jump}
      </button>
    </div>
  );
}
