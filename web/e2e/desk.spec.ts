/**
 * End-to-end test of decision items against a real crewmind server with the mock model: the CEO
 * proposes a requirement, the chairman sees it as a card in the chat and as an entry on the Desk,
 * accepts it from the card, and looks at the decision items and the agenda in the Plan panel.
 * It runs after board.spec.ts (one worker, files in name order) and reuses the signed-in session.
 *
 * Starting a project queues the CEO's first planning run at once, so the scripted proposal needs no
 * directive. The script names its runs one by one, so later runs do not propose again.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  IDLE_SCRIPT,
  STATE_FILE,
  createProject,
  expectAccessible,
  expectNoViolations,
  setWorkRuns,
  setWorkScript,
  toolTurn,
} from "./helpers";

test.describe.configure({ mode: "serial" });

const SLOW = 60_000;
const PROJECT = "Desk project";
const PROPOSAL = "The plan names a venue for the launch.";
const SUCCESS_TEST = "A reader finds the venue's name and address in plan.md.";

let page: Page;
let projectId = "";

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ storageState: STATE_FILE })).newPage();
});

test.afterAll(async () => {
  setWorkScript("CEO", IDLE_SCRIPT);
  await page.context().close();
});

const panel = (): Locator => page.getByTestId("panel");
const chatCard = (): Locator =>
  page.getByRole("log", { name: "Messages" }).locator('[data-testid="item-card"][data-item-kind="proposed scope"]');
const deskGroup = (): Locator => page.getByTestId("desk-project").filter({ has: page.getByRole("heading", { name: PROJECT }) });

test("a requirement the CEO proposes appears as a card in the chat", async () => {
  await createProject(page, PROJECT);
  projectId = new URL(page.url()).pathname.split("/").pop() ?? "";
  const settings = await page.request.post("/v1/settings/change_project", {
    data: {
      project_id: projectId,
      changes: { "authority.accept_scope": "chairman" },
      reason: "The chairman accepts scope in this test.",
    },
  });
  expect(settings.ok(), await settings.text()).toBe(true);
  setWorkRuns("CEO", [
    [
      toolTurn([
        "agent_propose_requirement",
        { text: PROPOSAL, test_kind: "observable", success_test: SUCCESS_TEST, estimate_runs: 2 },
      ]),
      { text: "Proposed." },
    ],
  ]);
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByTestId("project-state")).toHaveText("running");

  const card = chatCard();
  await expect(card).toBeVisible({ timeout: SLOW });
  await expect(card).toContainText(PROPOSAL);
  await expect(card.getByTestId("item-state")).toHaveText("State: open");
  await expect(card).toContainText("2 runs");
  await expect(card.getByTestId("item-deadline")).toHaveText(/^Answer by .+\. If you do nothing: it is declined\.$/);
  await expect(card.getByRole("button", { name: /^Accept “/ })).toBeVisible();
  await expect(card.getByRole("button", { name: /^Accept anyway “/ })).toBeVisible();
  await expect(card.getByRole("button", { name: /^Decline “/ })).toBeVisible();
  await expectAccessible(page, "decision card in the chat");
});

test("declining asks first, and Cancel leaves the item open", async () => {
  const card = chatCard();
  await card.getByRole("button", { name: /^Decline “/ }).click();
  const confirm = card.getByRole("group", { name: "Decline this?" });
  await expect(confirm.getByLabel("Your note (optional)")).toBeFocused();
  await expectNoViolations(page, "decision card, asking before declining");
  await confirm.getByRole("button", { name: "Cancel" }).click();
  await expect(confirm).toHaveCount(0);
  await expect(card.getByTestId("item-state")).toHaveText("State: open");
});

test("the Desk lists the proposal under its project, with what happens if nothing is done", async () => {
  await expect(page.getByTestId("desk-link")).toContainText(/Desk \([1-9]\d*\)/);
  await page.getByTestId("desk-link").click();
  await expect(page.getByRole("heading", { level: 1, name: "Desk" })).toBeVisible();

  const group = deskGroup();
  const entry = group.getByTestId("desk-entry").filter({ hasText: PROPOSAL });
  await expect(entry).toHaveCount(1);
  await expect(entry.getByTestId("item-deadline")).not.toBeEmpty();
  await expect(entry.getByRole("button", { name: /^Accept “/ })).toBeVisible();
  const snooze = entry.getByRole("group", { name: /^Set aside:/ });
  await expect(snooze.getByRole("button", { name: "1 hour" })).toBeEnabled();
  await expect(snooze.getByRole("button", { name: "Until tomorrow" })).toBeVisible();
  await expect(snooze.getByRole("button", { name: "3 days" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Daily brief" })).toBeVisible();
  await expectAccessible(page, "Desk");

  await group.getByRole("link", { name: /^Open the project/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: PROJECT })).toBeVisible();
});

test("accepting from the card shows the outcome, removes the buttons and clears the Desk entry", async () => {
  const card = chatCard();
  await card.getByRole("button", { name: /^Accept “/ }).click();
  await expect(card.getByTestId("item-outcome")).toBeVisible();
  await expect(card.getByTestId("item-state")).toHaveText("State: decided");
  await expect(card.getByRole("button")).toHaveCount(0);

  const desk = await page.request.get("/v1/desk/show");
  const waiting = ((await desk.json()) as { waiting: { project_id: string }[] }).waiting;
  expect(waiting.filter((entry) => entry.project_id === projectId)).toEqual([]);
});

test("the Plan panel lists the decision item with its history, and the agenda says when the clock next wakes an agent", async () => {
  await page.getByRole("button", { name: "Plan", exact: true }).click();
  await panel().getByRole("tab", { name: "Decision items" }).click();
  await expect(panel()).toContainText("Nothing is open.");
  await panel().getByRole("button", { name: "All", exact: true }).click();
  const item = panel().getByTestId("item").filter({ hasText: PROPOSAL });
  await expect(item).toHaveCount(1);
  await expect(item.getByTestId("item-state")).toHaveText("State: decided");
  await item.getByRole("button", { name: /^History/ }).click();
  await expect(item.getByTestId("item-history").getByRole("listitem").first()).toBeVisible();
  await expectNoViolations(page, "Plan decision items");

  await panel().getByRole("tab", { name: "Agenda" }).click();
  await expect(panel().getByTestId("next-wake")).toHaveText(
    /^(The next time the clock wakes an agent: .+|Nothing is scheduled to wake an agent\.)$/,
  );
  await expectNoViolations(page, "Plan agenda");

  await panel().getByRole("tab", { name: "Dates and budget" }).click();
  await expect(panel().getByTestId("spend")).toContainText(/Real-world spend/);
  await expectNoViolations(page, "Plan dates and budget with spend");
});
