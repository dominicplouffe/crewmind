/**
 * HUM-10, CHAT-18: every surface that says how much needs the person reads one desk list, so they
 * agree in every state. This renders the real shell and Home against a fake server and checks the
 * sidebar badge, the phone tab badge, Home's inbox count and summary, each project card and the
 * page title, then changes the desk and checks them again.
 */
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth";
import { ThemeProvider } from "../components/ThemeButton";
import { Home } from "../pages/Home";
import { AppShell } from "../shell/AppShell";
import { PaletteProvider } from "../shell/palette";
import { ProjectsProvider } from "../shell/projects";
import { NeedsYouProvider, useNeedsYou } from "./NeedsYou";

type Entry = { project_id: string; project_name: string; what: string; title: string; deadline: string | null; item: null };

let desk: Entry[] = [];

const projects = [
  { project_id: "p1", name: "Launch site", state: "running", type: "deliver", created_at: "2026-11-20T10:00:00Z", your_role: "chairman" },
  { project_id: "p2", name: "Market scan", state: "running", type: "explore", created_at: "2026-11-21T10:00:00Z", your_role: "chairman" },
];

function entry(project: (typeof projects)[number], title: string): Entry {
  return { project_id: project.project_id, project_name: project.name, what: "frozen thread", title, deadline: null, item: null };
}

function answer(url: string): unknown {
  const path = new URL(url, "http://localhost").pathname;
  switch (path) {
    case "/v1/auth/whoami":
      return { person_id: "me", name: "Dominic Plouffe", email: "dom@example.com", role: "admin", via: "session" };
    case "/v1/desk/show":
      return { waiting: desk };
    case "/v1/projects/list":
      return { items: projects, next: null };
    case "/v1/chat/header":
      return { state: "running", now: [], next: [], waiting_on_you: 0, budget: "0 of 100 tokens used (0%)", budget_spent: 0, budget_wall: 100, holds: [], notes: [], unread: 0 };
    case "/v1/brief/show":
      return { since: "2026-11-21T10:00:00Z", until: "2026-11-22T10:00:00Z", projects: [] };
    case "/v1/settings/show_install":
      return { scope: "install", items: [{ name: "founder.credential", value: "main", allowed: "", unit: null, version: 1 }] };
    case "/v1/credentials/list":
      return { items: [{ name: "main", kind: "model", provider: "anthropic", state: "ok", owner_id: "me", breaker: "closed", lineup: {} }] };
    default:
      return {};
  }
}

function Reload(): JSX.Element {
  const { reload } = useNeedsYou();
  return (
    <button type="button" onClick={reload}>
      reload desk
    </button>
  );
}

function renderApp(): void {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <NeedsYouProvider>
            <ProjectsProvider>
              <PaletteProvider>
                <AppShell>
                  <Routes>
                    <Route path="/" element={<Home />} />
                  </Routes>
                  <Reload />
                </AppShell>
              </PaletteProvider>
            </ProjectsProvider>
          </NeedsYouProvider>
        </AuthProvider>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

function shown(): {
  nav: string;
  tab: string;
  inbox: string;
  summary: string;
  cards: Record<string, string>;
  sidebar: Record<string, string>;
  title: string;
} {
  const nav = screen.getByTestId("nav-home").querySelector('[data-testid="nav-needs-count"] [aria-hidden="true"]')?.textContent ?? "0";
  const sidebar: Record<string, string> = {};
  for (const link of document.querySelectorAll(".sidebar-projects a")) {
    const name = link.querySelector(".project-item-name")?.textContent ?? "";
    sidebar[name] = (link.querySelector('[data-testid="nav-needs-count"] [aria-hidden="true"]')?.textContent ?? "0");
  }
  const tabBadge = document.querySelector(".tab-badge")?.textContent ?? "0";
  const inbox = screen.queryByTestId("inbox-count")?.textContent ?? "0";
  const cards: Record<string, string> = {};
  for (const card of screen.queryAllByTestId("project-card")) {
    const name = card.querySelector(".project-card-name")?.textContent ?? "";
    cards[name] = within(card).queryByText(/needs? you$/)?.textContent ?? "";
  }
  return {
    nav,
    tab: tabBadge,
    inbox,
    summary: screen.getByTestId("home-summary").textContent ?? "",
    cards,
    sidebar,
    title: document.title,
  };
}

beforeEach(() => {
  desk = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(answer(String(input))), { status: 200, headers: { "content-type": "application/json" } })),
  );
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {} }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("needs-you agreement across surfaces (HUM-10, CHAT-18)", () => {
  it("shows nothing anywhere when the desk is empty", async () => {
    renderApp();
    await waitFor(() => expect(screen.getByTestId("home-summary").textContent).toBe("Nothing needs you right now."));
    const now = shown();
    expect([now.nav, now.tab, now.inbox]).toEqual(["0", "0", "0"]);
    expect(now.title).toBe("Home · crewmind");
  });

  it("every count matches the desk, per project and in total, and follows it when it changes", async () => {
    const [first, second] = projects;
    if (!first || !second) throw new Error("fixture");
    desk = [entry(first, "Thread 1 is frozen"), entry(first, "Thread 2 is frozen"), entry(second, "Thread 3 is frozen")];
    renderApp();
    await waitFor(() => expect(screen.getByTestId("inbox-count").textContent).toBe("3"));
    await waitFor(() => expect(screen.getAllByTestId("project-card")).toHaveLength(2));
    let now = shown();
    expect(now.nav).toBe("3");
    expect(now.tab).toBe("3");
    expect(now.inbox).toBe("3");
    expect(now.summary).toContain("3 decisions wait on you across 2 projects");
    expect(now.cards).toEqual({ "Launch site": "2 need you", "Market scan": "1 needs you" });
    expect(now.sidebar).toEqual({ "Launch site": "2", "Market scan": "1" });
    expect(now.title).toBe("(3) Home · crewmind");
    expect(screen.getAllByTestId("desk-entry")).toHaveLength(3);

    desk = [entry(second, "Thread 3 is frozen")];
    await act(async () => {
      screen.getByRole("button", { name: "reload desk" }).click();
    });
    await waitFor(() => expect(screen.getByTestId("inbox-count").textContent).toBe("1"));
    now = shown();
    expect([now.nav, now.tab, now.inbox]).toEqual(["1", "1", "1"]);
    expect(now.cards).toEqual({ "Launch site": "", "Market scan": "1 needs you" });
    expect(now.sidebar).toEqual({ "Launch site": "0", "Market scan": "1" });
    expect(now.title).toBe("(1) Home · crewmind");
  });
});
