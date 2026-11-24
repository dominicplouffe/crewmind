import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AddSheet } from "./AddSheet";
import { ConnectionsPanel } from "./ConnectionsPanel";
import { daysUntil, healthOf, usageLine } from "./health";
import { ImportSheet } from "./ImportSheet";

const VALUE = "wp-app-password-0451";

interface Call {
  url: string;
  method: string;
  body: Record<string, unknown> | null;
}

let calls: Call[] = [];
let answers: Record<string, unknown> = {};

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
});

beforeEach(() => {
  calls = [];
  answers = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, method: init?.method ?? "GET", body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null });
      const key = Object.keys(answers).find((path) => url.startsWith(path));
      return new Response(JSON.stringify(key ? answers[key] : {}), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function item(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "c1",
    name: "wordpress",
    kind: "secret",
    scope: "project",
    description: "WordPress password.",
    state: "active",
    delivery: "sent_for_you",
    sites: ["example.com"],
    created_at: "2026-11-23T10:00:00Z",
    changed_at: "2026-11-23T10:00:00Z",
    used_in: 1,
    yours: true,
    ...extra,
  };
}

describe("health (CON-15)", () => {
  it("says expired, expiring, not used yet or working, in words", () => {
    const now = Date.parse("2026-11-23T12:00:00Z");
    expect(healthOf({ state: "expired", used_in: 1 }, now).label).toBe("Expired");
    expect(healthOf({ state: "active", expires_on: "2026-11-23", expires_soon: true, used_in: 1 }, now).label).toBe("Expires today");
    expect(healthOf({ state: "active", expires_on: "2026-11-26", expires_soon: true, used_in: 1 }, now).label).toBe("Expires in 3 days");
    expect(healthOf({ state: "active", expires_on: "2027-11-26", expires_soon: false, used_in: 0 }, now).label).toBe("Not in use");
    expect(healthOf({ state: "active", used_in: 1, last_used_at: "2026-11-23T11:00:00Z" }, now).label).toBe("Working");
    expect(healthOf({ state: "active", used_in: 2 }, now).label).toBe("Not used yet");
    expect(daysUntil("2026-11-24", now)).toBe(1);
  });

  it("says how each kind is used", () => {
    expect(usageLine({ kind: "secret", delivery: "sent_for_you", sites: ["a.com", "b.com"] })).toBe("Sent for you to a.com, b.com");
    expect(usageLine({ kind: "secret", delivery: "given", env_name: "KEY", shape: "file" })).toBe("Given to the agent as the file KEY");
    expect(usageLine({ kind: "variable", env_name: "REGION" })).toBe("Read as REGION");
  });
});

describe("AddSheet (CON-2, CON-4)", () => {
  it("adds a need's secret sent for you, with the roles that need it, and keeps the value in no attribute", async () => {
    answers["/v1/connections/add_secret"] = item();
    const onSaved = vi.fn();
    render(
      <AddSheet
        context={{ mode: "project", projectId: "p1", roles: [{ slug: "blog-writer", name: "Blog writer" }] }}
        preset={{ kind: "secret", name: "wordpress", roles: ["blog-writer"] }}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );
    expect(screen.getByLabelText("Name")).toHaveProperty("readOnly", true);
    expect(screen.getByLabelText("Blog writer")).toHaveProperty("checked", true);
    await userEvent.type(screen.getByLabelText("What is it for?"), "WordPress application password.");
    await userEvent.type(screen.getByLabelText("Sites"), "example.com, api.example.com");
    await userEvent.click(screen.getByRole("radio", { name: "User and password" }));
    await userEvent.type(screen.getByLabelText("User name"), "dom");
    const value = screen.getByLabelText("Value");
    expect(value).toHaveProperty("type", "password");
    await userEvent.type(value, VALUE);
    expect(value.getAttribute("value")).not.toBe(VALUE);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [sent] = calls;
    expect(sent?.url).toBe("/v1/connections/add_secret");
    expect(sent?.body).toMatchObject({
      name: "wordpress",
      value: VALUE,
      delivery: "sent_for_you",
      sites: ["example.com", "api.example.com"],
      header_kind: "basic",
      basic_user: "dom",
      scope: "project",
      project_id: "p1",
      roles: ["blog-writer"],
    });
  });

  it("will not save in a project until someone may use it", async () => {
    render(
      <AddSheet
        context={{ mode: "project", projectId: "p1", roles: [{ slug: "writer", name: "Writer" }] }}
        startKind="variable"
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Save" })).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByLabelText("Every role"));
    expect(screen.getByRole("button", { name: "Save" })).toHaveProperty("disabled", false);
  });
});

describe("ImportSheet (CON-2)", () => {
  it("reviews names and kinds, lets a line be skipped, then saves all at once", async () => {
    answers["/v1/connections/review_env"] = {
      saved: 0,
      lines: [
        { line: 1, name: "API_KEY", kind: "secret", skipped: false, problem: null },
        { line: 2, name: "SHORT_TOKEN", kind: "secret", skipped: false, problem: "too short" },
      ],
    };
    answers["/v1/connections/import_env"] = { saved: 1, lines: [] };
    const onSaved = vi.fn();
    render(<ImportSheet scope="person" onClose={vi.fn()} onSaved={onSaved} />);
    await userEvent.type(screen.getByLabelText("Lines to add"), "API_KEY=x");
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    const table = await screen.findByTestId("import-review");
    expect(within(table).getByText("too short")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Add 2 connections/ })).toHaveProperty("disabled", true);
    answers["/v1/connections/review_env"] = {
      saved: 0,
      lines: [
        { line: 1, name: "API_KEY", kind: "secret", skipped: false, problem: null },
        { line: 2, name: "SHORT_TOKEN", kind: "secret", skipped: true, problem: null },
      ],
    };
    await userEvent.click(screen.getByLabelText("Skip SHORT_TOKEN"));
    await waitFor(() => expect(screen.getByRole("button", { name: /Add 1 connection$/ })).toHaveProperty("disabled", false));
    await userEvent.click(screen.getByRole("button", { name: /Add 1 connection$/ }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(1));
    const saved = calls.find((call) => call.url === "/v1/connections/import_env");
    expect(saved?.method).toBe("POST");
    expect(saved?.body).toMatchObject({ skip: ["SHORT_TOKEN"], scope: "person" });
    expect(calls.every((call) => !call.url.includes("API_KEY"))).toBe(true);
  });
});

describe("ConnectionsPanel (CON-5, CON-14)", () => {
  it("leads with what is missing and who waits, and adds it in place", async () => {
    answers["/v1/connections/for_project"] = {
      attached: [],
      available: [],
      needs: [{ kind: "secret", name: "wordpress", roles: ["blog-writer"], state: "waived", seats: ["Ada"] }],
      roles: [{ slug: "blog-writer", name: "Blog writer" }],
    };
    render(<ConnectionsPanel projectId="p1" changes={0} onChanged={vi.fn()} />);
    const missing = await screen.findByTestId("need-missing");
    expect(within(missing).getByText("Waits: Ada")).toBeTruthy();
    expect(within(missing).getByText(/Needed by Blog writer/)).toBeTruthy();
    await userEvent.click(within(missing).getByRole("button", { name: /Add secret/ }));
    const sheet = await screen.findByTestId("add-connection");
    expect(within(sheet).getByLabelText("Name")).toHaveProperty("value", "wordpress");
    expect(within(sheet).getByLabelText("Blog writer")).toHaveProperty("checked", true);
  });

  it("marks a need done when it was added under other names, and takes it back", async () => {
    answers["/v1/connections/for_project"] = {
      attached: [],
      available: [],
      needs: [
        { kind: "secret", name: "wordpress", roles: ["blog-writer"], state: "open", seats: ["Ada"] },
        { kind: "variable", name: "site", roles: ["blog-writer"], state: "done", seats: [] },
      ],
      roles: [{ slug: "blog-writer", name: "Blog writer" }],
    };
    const onChanged = vi.fn();
    render(<ConnectionsPanel projectId="p1" changes={0} onChanged={onChanged} />);
    const missing = await screen.findByTestId("need-missing");
    await userEvent.click(within(missing).getByRole("button", { name: "It's added: wordpress" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const marked = calls.find((call) => call.url === "/v1/connections/mark_need_done");
    expect(marked?.body).toEqual({ project_id: "p1", need: "wordpress", kind: "secret" });
    const done = screen.getByTestId("need-done");
    expect(within(done).getByText("site")).toBeTruthy();
    await userEvent.click(within(done).getByRole("button", { name: "Not added after all: site" }));
    await waitFor(() => expect(calls.some((call) => call.url === "/v1/connections/reopen_need")).toBe(true));
  });
});
