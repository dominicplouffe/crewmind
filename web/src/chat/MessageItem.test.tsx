import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Message } from "../api/client";
import { MessageItem, type MessageHandlers } from "./MessageItem";

afterEach(cleanup);

function message(extra: Partial<Message>): Message {
  return {
    id: 4, channel: "project chat", author_kind: "person", author: "Admin", kind: "message", body: "Use metric units.",
    reply_to: null, thread_id: null, run_id: null, detail: null, at: "2026-01-01T00:00:00Z", ...extra,
  };
}

function handlers(): MessageHandlers {
  return {
    onReply: vi.fn(), onThread: vi.fn(), onJump: vi.fn(), onPreview: vi.fn(), onTrace: vi.fn(),
    onAccept: vi.fn(), onDismiss: vi.fn(), onPin: vi.fn(), onExample: vi.fn(), onFix: vi.fn(),
    onDecide: vi.fn(), onOrder: vi.fn(), onRequest: vi.fn(),
  };
}

function show(item: Message, extra: Partial<Parameters<typeof MessageItem>[0]> = {}): MessageHandlers {
  const all = handlers();
  render(<MessageItem message={item} parent={undefined} card={undefined} replies={0} handlers={all} {...extra} />);
  return all;
}

describe("message actions (CHAT-8)", () => {
  it("keeps the less common actions in a menu that the keyboard can open, walk and close", async () => {
    const user = userEvent.setup();
    const all = show(message({}));
    expect(screen.queryByRole("menu")).toBeNull();
    const more = screen.getByRole("button", { name: /More\s*actions for the message from Admin/ });
    more.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("menuitem", { name: "Pin as a standing order" })).toHaveProperty("tabIndex", -1);
    expect(document.activeElement?.textContent).toBe("Pin as a standing order");
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement?.textContent).toBe("Mark as an example");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(more);

    await user.keyboard("{ArrowDown}{End}{Enter}");
    expect(all.onDecide).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("offers “Not what I asked” on an agent's message only", async () => {
    const user = userEvent.setup();
    const all = show(message({ author_kind: "agent", author: "CEO" }));
    await user.click(screen.getByRole("button", { name: /More/ }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Not what I asked"]);
    await user.click(screen.getByRole("menuitem", { name: "Not what I asked" }));
    expect(all.onFix).toHaveBeenCalledOnce();
  });

  it("offers to remove the mark on an example, whether the server or this page says it is one", async () => {
    const user = userEvent.setup();
    show(message({ kind: "status", detail: { kind: "example" } }));
    expect(screen.getByTestId("marker-example").textContent).toBe("Example");
    await user.click(screen.getByRole("button", { name: /More/ }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Remove example mark"]);
    cleanup();
    show(message({}), { example: true });
    expect(screen.getByTestId("marker-example")).toBeTruthy();
  });

  it("has no menu on a status line from nightsquad", () => {
    show(message({ author_kind: "platform", author: "nightsquad", kind: "status" }));
    expect(screen.queryByRole("button", { name: /More/ })).toBeNull();
  });
});

describe("markers and status buttons", () => {
  it("marks a long or unclear reply and a held report", () => {
    show(message({ author_kind: "agent", author: "CEO", detail: { kind: "held report", lint: "unclear" } }));
    expect(screen.getByTestId("marker-lint").textContent).toBe("unclear");
    expect(screen.getByTestId("marker-held").textContent).toBe("Sent at the reporting time");
  });

  it("puts Confirm, Edit and Discard on a proposed order while it is proposed", async () => {
    const user = userEvent.setup();
    const status = message({ author_kind: "platform", kind: "status", detail: { kind: "standing order proposed", order: 3 } });
    const order = { id: 3, text: "Use metric units.", state: "proposed", proposed_by: "CEO", being_shortened: false };
    const all = show(status, { order });
    await user.click(screen.getByRole("button", { name: /^Edit\s*standing order 3$/ }));
    await user.click(screen.getByRole("button", { name: /^Discard\s*standing order 3$/ }));
    await user.click(screen.getByRole("button", { name: /^Confirm\s*standing order 3$/ }));
    expect(all.onOrder).toHaveBeenNthCalledWith(1, 3, "edit");
    expect(all.onOrder).toHaveBeenNthCalledWith(2, 3, "discard");
    expect(all.onOrder).toHaveBeenNthCalledWith(3, 3, "confirm");
    cleanup();
    show(status, { order: { ...order, state: "active" } });
    expect(screen.queryByRole("button", { name: /Confirm/ })).toBeNull();
    expect(screen.getByText("This standing order is now in force.")).toBeTruthy();
  });

  it("puts Approve and Decline on an open reopen request", async () => {
    const user = userEvent.setup();
    const status = message({ author_kind: "platform", kind: "status", detail: { kind: "reopen request", request: 2, decision: 1 } });
    const request = { id: 2, decision_id: 1, by: "CEO", reason: "New numbers.", evidence: [], approved: null, at: "2026-01-01T00:00:00Z" };
    const all = show(status, { request });
    await user.click(screen.getByRole("button", { name: /^Decline\s*reopen request 2$/ }));
    expect(all.onRequest).toHaveBeenCalledWith(2, false);
    cleanup();
    show(status, { request: { ...request, approved: true } });
    expect(screen.getByText("You approved this request.")).toBeTruthy();
  });
});

describe("lines said while drafting (FND-1)", () => {
  it("shows a copied drafting line as said, by whom, without the server's prefix, as a record with no actions", () => {
    show(
      message({
        author_kind: "platform",
        author: "nightsquad",
        kind: "status",
        body: "The Founder: Here is a first draft.",
        detail: { kind: "drafting", author: "founder" },
      }),
    );
    const line = screen.getByTestId("message-drafting");
    expect(line.dataset.author).toBe("founder");
    expect(line.textContent).toContain("The Founder");
    expect(line.textContent).toContain("While drafting");
    expect(line.textContent).toContain("Here is a first draft.");
    expect(line.textContent).not.toContain("The Founder: Here");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("puts the person's own drafting words on their side", () => {
    show(message({ author_kind: "platform", kind: "status", body: "You: A daily post.", detail: { kind: "drafting", author: "person" } }));
    const line = screen.getByTestId("message-drafting");
    expect(line.className).toContain("from-person");
    expect(line.textContent).toContain("A daily post.");
    expect(line.textContent).not.toContain("You: A daily");
  });
});

describe("groups and reply quotes (CHAT-3, CHAT-10, CHAT-11)", () => {
  it("shows a grouped agent message without its avatar and name, and its time on hover", () => {
    show(message({ author_kind: "agent", author: "CEO", body: "And one more thing." }), { continued: true });
    const item = screen.getByTestId("message-agent");
    expect(item.className).toContain("is-continued");
    expect(item.querySelector(".author")).toBeNull();
    expect(item.querySelector(".gutter-time")).not.toBeNull();
    // The name stays in the message's label for screen readers.
    expect(item.getAttribute("aria-label")).toContain("CEO");
  });

  it("keeps the delivered mark on a person's grouped message", () => {
    show(message({}), { continued: true });
    expect(screen.getByTestId("delivered")).toBeTruthy();
    expect(screen.getByTestId("message-person").querySelector(".author")).toBeNull();
  });

  it("quotes a reply's question only when asked to, and says “you” for the signed-in person's words", () => {
    const parent = message({ id: 2, body: "Are you there?" });
    show(message({ author_kind: "agent", author: "CEO", reply_to: 2 }), { parent, parentMine: true });
    expect(screen.getByRole("button", { name: /In reply to you/ })).toBeTruthy();
    cleanup();
    show(message({ author_kind: "agent", author: "CEO", reply_to: 2 }), { parent, showQuote: false });
    expect(screen.queryByRole("button", { name: /In reply to/ })).toBeNull();
    expect(screen.getByTestId("message-agent").dataset.replyTo).toBe("2");
  });
});
