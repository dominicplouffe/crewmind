import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AddMcpSheet } from "./AddMcpSheet";
import { McpTools } from "./McpTools";

vi.mock("../auth", () => ({ useAuth: () => ({ person: null, reload: async () => {} }) }));

const TOKEN = "mcp-token-0042";

interface Call {
  url: string;
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
      calls.push({ url, body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null });
      const key = Object.keys(answers).find((path) => url.startsWith(path));
      return new Response(JSON.stringify(key ? answers[key] : {}), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function server(tools: { name: string; classification: string; permission: string }[]): Record<string, unknown> {
  return {
    id: "m1",
    name: "blog",
    kind: "mcp_server",
    scope: "person",
    description: "Blog tools.",
    state: "active",
    created_at: "2026-11-23T10:00:00Z",
    changed_at: "2026-11-23T10:00:00Z",
    used_in: 0,
    yours: true,
    mcp: {
      url: "https://mcp.example.com/mcp",
      transport: "streamable_http",
      auth_kind: "bearer",
      header_name: null,
      private_allowed: false,
      state: "active",
      server_name: "blog tools",
      server_version: "1.0",
      last_error: null,
      tools_refreshed_at: null,
      tools: tools.map((tool) => ({ title: null, description: "Does a thing.", gone: false, ...tool })),
    },
  };
}

describe("AddMcpSheet (CON-9, CON-15)", () => {
  it("tests the server before saving, then saves with the token, which stays out of the markup", async () => {
    answers["/v1/connections/test_mcp_server"] = {
      transport: "streamable_http",
      server_name: "blog tools",
      server_version: "1.0",
      tools: [
        { name: "list_posts", title: null, description: "", reads_only: true },
        { name: "create_post", title: null, description: "", reads_only: false },
      ],
    };
    answers["/v1/connections/add_mcp_server"] = server([]);
    const onSaved = vi.fn();
    render(
      <AddMcpSheet context={{ mode: "settings", scope: "person" }} onClose={vi.fn()} onSaved={onSaved} />,
    );
    await userEvent.type(screen.getByLabelText("Name", { exact: true }), "blog");
    await userEvent.type(screen.getByLabelText("What is it for?"), "Blog tools.");
    await userEvent.type(screen.getByLabelText("Address"), "https://mcp.example.com/mcp");
    await userEvent.click(screen.getByLabelText(/Bearer token/));
    const token = screen.getByLabelText("Token", { exact: true });
    await userEvent.type(token, TOKEN);
    expect(token.getAttribute("value")).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    const probe = await screen.findByTestId("mcp-probe");
    expect(within(probe).getByText("blog tools answered with 2 tools.")).toBeTruthy();
    expect(within(probe).getByText("Changes things")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const added = calls.find((call) => call.url === "/v1/connections/add_mcp_server");
    expect(added?.body).toMatchObject({ url: "https://mcp.example.com/mcp", auth_kind: "bearer", value: TOKEN, name: "blog" });
  });

  it("needs a new test when the address or sign-in changes", async () => {
    answers["/v1/connections/test_mcp_server"] = { transport: "sse", server_name: "x", server_version: null, tools: [] };
    render(
      <AddMcpSheet context={{ mode: "settings", scope: "person" }} onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText("Address"), "https://a.example.com/mcp");
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await screen.findByTestId("mcp-probe");
    await userEvent.type(screen.getByLabelText("Address"), "x");
    expect(screen.queryByTestId("mcp-probe")).toBeNull();
  });

  it("adds a command server whose variables name a secret, never a typed value (CON-11)", async () => {
    answers["/v1/connections/list"] = {
      items: [{ ...server([]), id: "s1", name: "github", kind: "secret", mcp: null }],
    };
    answers["/v1/connections/add_command_mcp_server"] = server([]);
    const onSaved = vi.fn();
    render(<AddMcpSheet context={{ mode: "settings", scope: "person" }} onClose={vi.fn()} onSaved={onSaved} />);
    await userEvent.type(screen.getByLabelText("Name", { exact: true }), "gh");
    await userEvent.type(screen.getByLabelText("What is it for?"), "GitHub tools.");
    await userEvent.click(screen.getByLabelText(/Command/, { selector: "input[type=radio]" }));
    expect(screen.queryByLabelText("Address")).toBeNull();
    await userEvent.type(screen.getByLabelText("Command", { exact: true }), "npx -y github-mcp");
    await userEvent.click(screen.getByRole("button", { name: /Add a variable/ }));
    await userEvent.type(screen.getByLabelText("Variable 1 name"), "GITHUB_TOKEN");
    await userEvent.selectOptions(await screen.findByLabelText("Filled by, for GITHUB_TOKEN"), "s1");
    await userEvent.click(screen.getByRole("button", { name: "Test and save" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const added = calls.find((call) => call.url === "/v1/connections/add_command_mcp_server");
    expect(added?.body).toMatchObject({ command: "npx -y github-mcp", environment: { GITHUB_TOKEN: "s1" }, image: null });
  });
});

describe("McpTools (CON-12, INT-4)", () => {
  it("allows a reading tool at once and asks before allowing one that changes things", async () => {
    const onChanged = vi.fn();
    const item = server([
      { name: "list_posts", classification: "read", permission: "denied" },
      { name: "create_post", classification: "write", permission: "denied" },
    ]);
    render(<McpTools item={item as never} onChanged={onChanged} />);
    await userEvent.click(screen.getByText(/0 of 2 tools allowed/));
    await userEvent.click(screen.getByRole("switch", { name: "Allow list_posts" }));
    await waitFor(() => expect(calls.at(-1)?.url).toBe("/v1/connections/allow_tool"));
    await userEvent.click(screen.getByRole("switch", { name: "Allow create_post" }));
    const dialog = await screen.findByTestId("allow-tool");
    expect(within(dialog).getByText(/It may change things/)).toBeTruthy();
    expect(calls.filter((call) => call.body?.tool === "create_post")).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Allow it" }));
    await waitFor(() => expect(calls.at(-1)?.body).toMatchObject({ tool: "create_post" }));
  });
});

describe("PresetPicker (CON-15)", () => {
  it("fills in a known server and says which secret to create", async () => {
    answers["/v1/connections/presets"] = {
      presets: [
        {
          slug: "github",
          name: "github",
          title: "GitHub",
          description: "Issues and pull requests.",
          kind: "remote",
          url: "https://api.githubcopilot.com/mcp/",
          auth_kind: "bearer",
          header_name: null,
          value_needed: { name: "github-token", description: "A fine-grained token." },
          command: null,
          environment: [],
          docs: "https://github.com/github/github-mcp-server",
          hidden: false,
        },
      ],
    };
    render(<AddMcpSheet context={{ mode: "settings", scope: "person" }} onClose={vi.fn()} onSaved={vi.fn()} />);
    await userEvent.selectOptions(await screen.findByLabelText("Start from a known server"), "github");
    expect((screen.getByLabelText("Address") as HTMLInputElement).value).toBe("https://api.githubcopilot.com/mcp/");
    expect((screen.getByLabelText("Name", { exact: true }) as HTMLInputElement).value).toBe("github");
    expect(screen.getByLabelText("Token", { exact: true })).toBeTruthy();
    expect(within(screen.getByTestId("preset-note")).getByText("You need: A fine-grained token.")).toBeTruthy();
  });
});
