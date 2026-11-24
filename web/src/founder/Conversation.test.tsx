import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Conversation } from "./Conversation";
import type { Line } from "./logic";

afterEach(cleanup);
// The test DOM has no layout, so no scrolling; the page scrolls in a real browser.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const asked: Line = { id: 1, author: "person", body: "What will you use for the hero images?", detail: null, at: "2026-11-24T21:19:00Z" };

describe("the Founder is never silent while it works on a message (FND-1, P17)", () => {
  it("shows a thinking bubble with what it is doing until its words start to arrive", () => {
    render(<Conversation lines={[asked]} reply="" thinking={{ doing: "reading the draft", since: new Date().toISOString() }} />);
    const bubble = screen.getByTestId("founder-thinking");
    expect(bubble.textContent).toContain("The Founder");
    expect(bubble.textContent).toContain("thinking");
    expect(screen.getByTestId("waiting-for-founder").textContent).toContain("reading the draft");
  });

  it("says it is working even before it reports a step", () => {
    render(<Conversation lines={[asked]} reply="" thinking={{ doing: "", since: "" }} />);
    expect(screen.getByTestId("waiting-for-founder").textContent).toContain("The Founder is working on it");
  });

  it("gives way to the reply as it is written, and shows nothing when no turn is owed", () => {
    render(<Conversation lines={[asked]} reply="I will use" thinking={{ doing: "", since: "" }} />);
    expect(screen.queryByTestId("founder-thinking")).toBeNull();
    expect(screen.getByTestId("founder-reply").textContent).toContain("I will use");
    cleanup();
    render(<Conversation lines={[asked]} reply="" thinking={null} />);
    expect(screen.queryByTestId("founder-thinking")).toBeNull();
  });
});
