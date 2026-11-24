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
