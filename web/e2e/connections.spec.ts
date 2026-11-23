/**
 * End-to-end tests of connections against a real crewmind server: Settings → Connections (empty
 * state, add a secret sent for you, add a variable, paste a .env), and a project's Connections
 * panel (attach with roles). Covers CON-2, CON-3, CON-4, CON-15, NFR-18.
 * It runs after app.spec.ts (one worker, files in name order) and reuses its signed-in session.
 */
import { expect, test, type Page } from "@playwright/test";
import { STATE_FILE, createProject, expectAccessible, openPanel } from "./helpers";

test.describe.configure({ mode: "serial" });

const VALUE = "e2e-secret-value-7731-unguessable";
const SHOTS = process.env.CREWMIND_E2E_SHOTS;

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ storageState: STATE_FILE, viewport: { width: 1440, height: 900 } })).newPage();
});

test.afterAll(async () => {
  await page.context().close();
});

async function shot(name: string): Promise<void> {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

test("the empty Connections section teaches the kinds and is accessible (CON-15)", async () => {
  await page.goto("/settings/connections");
  await expect(page.getByTestId("connections-empty")).toBeVisible();
  await expect(page.getByRole("paragraph").filter({ hasText: "A secret sent for you" })).toBeVisible();
  await shot("01-settings-empty");
  await expectAccessible(page, "connections, empty");
});

test("a secret sent for you is added once and its value never shows again (CON-2)", async () => {
  await page.getByRole("button", { name: /^Add A secret sent for you/ }).click();
  const sheet = page.getByTestId("add-connection");
  await sheet.getByLabel("Name", { exact: true }).fill("wordpress");
  await sheet.getByLabel("What is it for?").fill("WordPress application password for the blog.");
  await sheet.getByLabel("Sites", { exact: true }).fill("example.com");
  await sheet.getByRole("radio", { name: "User and password" }).click();
  await sheet.getByLabel("User name", { exact: true }).fill("dom");
  await sheet.getByLabel("Value", { exact: true }).fill(VALUE);
  await shot("02-add-secret");
  await expectAccessible(page, "add a secret");
  await sheet.getByRole("button", { name: "Save" }).click();
  await expect(sheet).toBeHidden();
  const row = page.getByTestId("connection").filter({ hasText: "wordpress" });
  await expect(row).toContainText("Sent for you to example.com");
  expect(await page.content()).not.toContain(VALUE);
  await shot("03-settings-list");
});

test("a variable shows its value, and a pasted .env is reviewed before saving (CON-3, CON-2)", async () => {
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const sheet = page.getByTestId("add-connection");
  await sheet.getByRole("radio", { name: "Variable" }).check();
  await sheet.getByLabel("Name", { exact: true }).fill("region");
  await sheet.getByLabel("What is it for?").fill("Where the blog's readers are.");
  await sheet.getByLabel("Value", { exact: true }).fill("ca-east");
  await sheet.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("connection").filter({ hasText: "region" })).toContainText("ca-east");

  await page.getByRole("button", { name: "Paste a .env" }).click();
  const paste = page.getByTestId("import-env");
  await paste.getByLabel("Lines to add").fill(`OPENAI_API_KEY=${VALUE}\nTIMEZONE=America/Toronto\nTOKEN=short`);
  await paste.getByRole("button", { name: "Review" }).click();
  await expect(paste.getByTestId("import-review")).toBeVisible();
  await shot("04-env-review");
  await expectAccessible(page, "env review");
  await paste.getByLabel("Skip TOKEN").check();
  await paste.getByRole("button", { name: "Add 2 connections" }).click();
  await expect(paste).toBeHidden();
  await expect(page.getByText("2 connections added.")).toBeVisible();
  expect(await page.content()).not.toContain(VALUE);
});

test("a project's Connections panel attaches what is yours, with the roles chosen (CON-4)", async () => {
  await createProject(page, "Connections demo");
  await openPanel(page, "Connections");
  const panel = page.getByTestId("connections-panel");
  await expect(panel.getByText("Ready to attach")).toBeVisible();
  const row = panel.getByTestId("connection").filter({ hasText: "region" });
  await row.getByRole("button", { name: /Attach/ }).click();
  await row.locator("label.chip", { hasText: "Every role" }).click();
  await expect(row.getByLabel("Every role")).toBeChecked();
  await row.getByRole("button", { name: "Attach", exact: true }).click();
  await expect(panel.getByText("region is attached.", { exact: false })).toBeVisible();
  const attached = panel.getByRole("region", { name: "In this project" });
  await expect(attached.getByTestId("connection").filter({ hasText: "region" })).toContainText("Every role");
  await shot("05-project-panel");
  await expectAccessible(page, "project connections");
});
