/**
 * HUM-1, HUM-2, P4: the compact decision card leads with the ask in plain words, keeps the filer's
 * words as plain text, hides the rest behind "Details", and folds to one quiet line once settled.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { ItemCard } from "./ItemCard";
import type { Item } from "./logic";

const LATER = new Date(Date.now() + 3 * 24 * 3600 * 1000).toISOString();

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 7,
    project_id: "p1",
    kind: "approval: spend",
    title: "Spend 15.00 USD",
    state: "open",
    filed_by: "agent",
    fields: { amount: 15, currency: "USD" },
    recommendation: "Approve $15 a month for Postmark <a href='https://evil.example'>here</a>.",
    if_declined: "We use Amazon SES instead.",
    basis: null,
    actions: ["approve", "deny"],
    deadline: LATER,
    default_outcome: "deny",
    outcome: null,
    chairman_note: null,
    opened_at: new Date().toISOString(),
    closed_at: null,
    waits_on_you: true,
    ...overrides,
  };
}

function show(view: Item): HTMLElement {
  render(
    <MemoryRouter>
      <ItemCard item={view} onChanged={() => undefined} project={{ id: "p1", name: "Launch site" }} />
    </MemoryRouter>,
  );
  return screen.getByTestId("item-card");
}

afterEach(cleanup);

describe("the compact decision card (HUM-1, HUM-2)", () => {
  it("leads with the ask, the subject, who asks, by when and the project, with one primary action", () => {
    const card = show(item());
    expect(within(card).getByRole("heading", { level: 3 }).textContent).toMatch(/^Approve spending .*15\.00\?$/);
    expect(card.textContent).toContain("Launch site");
    expect(within(card).getByTestId("item-deadline").textContent).toMatch(/^Decide by .+ · in \d+ days$/);
    expect(within(card).getByTestId("item-state").textContent).toBe("State: open");
    const approve = within(card).getByRole("button", { name: /^Approve ?“Spend 15.00 USD”$/ });
    expect(approve.className).toContain("primary");
    expect(within(card).getByRole("button", { name: /^Deny ?“Spend 15.00 USD”$/ }).className).not.toContain("primary");
  });

  it("shows the filer's words as plain text, never as a link (P4)", () => {
    const card = show(item());
    expect(card.querySelector("a[href^='https://evil']")).toBeNull();
    expect(card.textContent).toContain("<a href='https://evil.example'>here</a>");
  });

  it("keeps the details out of sight until asked, and the server's title among them", () => {
    const card = show(item());
    const toggle = within(card).getByRole("button", { name: /^Details/ });
    const details = card.querySelector(".dcard-details") as HTMLElement;
    expect(details.hidden).toBe(true);
    expect(within(card).getByTestId("item-default").textContent).toBe("If you do nothing: it is denied.");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(details.hidden).toBe(false);
    expect(details.textContent).toContain("Spend 15.00 USD");
    expect(details.textContent).toContain("We use Amazon SES instead.");
  });

  it("offers a question's options as a choice with the recommended one chosen", () => {
    const card = show(
      item({
        kind: "question",
        title: "Question about other",
        fields: { question: "Yearly price too?", options: ["No", "Yes"], recommended: 2, default: "No", why: "A row more." },
        actions: ["answer"],
      }),
    );
    expect(within(card).getByRole("heading", { level: 3 }).textContent).toBe("Answer a question");
    const radios = within(card).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((radio) => radio.checked)).toEqual([false, true]);
    expect(within(card).getByRole("button", { name: /^Answer ?“Question about other”$/ })).toBeTruthy();
    expect(within(card).queryByRole("textbox")).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: "Answer in your own words" }));
    expect(within(card).getByRole("textbox", { name: "Your answer, in your own words" })).toBeTruthy();
  });

  it("folds to one quiet line once settled, with no buttons", () => {
    const card = show(item({ state: "decided", outcome: "approve", actions: [], closed_at: new Date().toISOString(), waits_on_you: false }));
    expect(within(card).getByTestId("item-outcome").textContent).toBe("You approved");
    expect(within(card).getByTestId("item-state").textContent).toBe("State: decided");
    expect(within(card).queryAllByRole("button")).toHaveLength(0);
  });
});
