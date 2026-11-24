import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DraftNeeds } from "./DraftNeeds";

afterEach(cleanup);

describe("DraftNeeds (FND-9, CON-14)", () => {
  it("shows each need as had or missing, and links to Connections only when one is missing", () => {
    render(
      <DraftNeeds
        needs={[
          { kind: "secret", name: "wordpress", roles: ["blog-writer"], have: true, granted: true },
          { kind: "mcp_server", name: "github", roles: ["developer"], have: false, granted: false },
        ]}
      />,
    );
    const [had, missing] = screen.getAllByTestId("draft-need") as [HTMLElement, HTMLElement];
    expect(within(had).getByText("You have it; attached at creation")).toBeTruthy();
    expect(within(missing).getByText("Missing")).toBeTruthy();
    expect(within(missing).getByText("MCP server, for developer")).toBeTruthy();
    const link = screen.getByRole("link", { name: /Add what's missing in Connections/ });
    expect(link.getAttribute("href")).toBe("/settings/connections");
  });

  it("says nothing when the squad needs nothing from outside", () => {
    const { container } = render(<DraftNeeds needs={[]} />);
    expect(container.textContent).toBe("");
  });
});
