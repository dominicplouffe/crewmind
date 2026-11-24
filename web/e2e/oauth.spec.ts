/**
 * End-to-end test of approving an AI client (OAuth for MCP) against a real Nightsquad server: a client
 * registers, the server sends the browser to the approval page, the person approves, and the browser
 * is sent back to the client with a one-time code. The approved client is then revoked in Settings.
 * It reuses the signed-in session and an existing project; nothing listens on the client's address.
 */
import { createHash, randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";
import { STATE_FILE, createProject, expectAccessible, expectNoViolations, openPanel } from "./helpers";

test.use({ storageState: STATE_FILE });

const CALLBACK = "http://localhost:7777/callback";
const CLIENT_NAME = "Test MCP client";

test("approve an AI client for fewer scopes than it asked, land on its callback with a code, then revoke it", async ({
  page,
  baseURL,
}) => {
  const registered = await page.request.post("/oauth/register", {
    data: { client_name: CLIENT_NAME, redirect_uris: [CALLBACK] },
  });
  expect(registered.ok(), await registered.text()).toBe(true);
  const clientId = ((await registered.json()) as { client_id: string }).client_id;

  const verifier = randomBytes(32).toString("base64url");
  const query = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: CALLBACK,
    scope: "read steer",
    code_challenge: createHash("sha256").update(verifier).digest("base64url"),
    code_challenge_method: "S256",
    resource: `${baseURL}/mcp`,
    state: "state-123",
  });
  let landed = "";
  await page.route("http://localhost:7777/**", (route) => {
    landed = route.request().url();
    return route.fulfill({ contentType: "text/plain", body: "The client took over." });
  });

  // The server sends the browser from its authorize address to the approval page in the app.
  await page.goto(`/oauth/authorize?${query.toString()}`);
  await expect(page.getByRole("heading", { level: 1, name: "An AI client asks to act for you" })).toBeVisible();
  await expect(page.getByTestId("oauth-client")).toHaveText(clientId);
  await expect(page.getByTestId("oauth-redirect")).toHaveText(CALLBACK);
  const scopes = page.getByRole("group", { name: "What it may do" });
  await expect(scopes.getByRole("checkbox")).toHaveCount(2);
  await expect(scopes.getByRole("checkbox", { name: "Read" })).toBeChecked();
  await expect(scopes).toContainText("Chat, decide items, and start and hold projects.");
  await expectAccessible(page, "approve an AI client");

  await scopes.getByRole("checkbox", { name: "Steer" }).uncheck();
  await page.getByRole("button", { name: "Approve" }).click();
  await page.waitForURL(/^http:\/\/localhost:7777\/callback\?/);
  const back = new URL(landed);
  expect(back.searchParams.get("code")).toBeTruthy();
  expect(back.searchParams.get("state")).toBe("state-123");

  // The client trades the code for its tokens, as it would on its own machine. From then on it is
  // listed in Settings with the scope that was left ticked, and can be revoked.
  const tokens = await page.request.post("/oauth/token", {
    form: {
      grant_type: "authorization_code",
      client_id: clientId,
      code: back.searchParams.get("code") ?? "",
      redirect_uri: CALLBACK,
      code_verifier: verifier,
      resource: `${baseURL}/mcp`,
    },
  });
  expect(tokens.ok(), await tokens.text()).toBe(true);
  await createProject(page, "OAuth project");
  await openPanel(page, "Settings");
  const client = page.getByTestId("approved-client").filter({ hasText: CLIENT_NAME });
  await expect(client).toContainText("May: Read ·");
  await client.getByRole("button", { name: /^Revoke/ }).click();
  await expectNoViolations(page, "asking before revoking an AI client");
  await client.getByRole("group").getByRole("button", { name: "Revoke" }).click();
  await expect(client).toHaveCount(0);
  await expect(page.getByTestId("approved-clients")).toContainText("You have approved no AI clients.");
});

test("denying sends the browser back to the client with an error and the state", async ({ page }) => {
  await page.route("http://localhost:7777/**", (route) => route.fulfill({ contentType: "text/plain", body: "Denied." }));
  await page.goto(`/#/oauth/approve?client_id=some-client&redirect_uri=${encodeURIComponent(CALLBACK)}&scope=read&state=s1`);
  await page.getByRole("button", { name: "Deny" }).click();
  await page.waitForURL("http://localhost:7777/callback?error=access_denied&state=s1");
});
