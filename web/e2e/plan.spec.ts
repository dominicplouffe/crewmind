/**
 * End-to-end test of the Plan panel against a real crewmind server with the mock model: the chairman
 * adds requirements, sees what is not ready and the longest chain, sets a target date and cuts scope.
 * It runs after the other specs (one worker, files in name order) and reuses the signed-in session.
 * The project stays a draft, so no agent runs and nothing here waits on one.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import { STATE_FILE, createProject, expectNoViolations, setTheme } from "./helpers";

test.describe.configure({ mode: "serial" });

const FIRST = "The plan lists three numbered steps.";
const SECOND = "The plan names an owner for every step.";
const CUT_REASON = "Owners are decided later.";

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ storageState: STATE_FILE })).newPage();
});

test.afterAll(async () => {
  await page.context().close();
});

const panel = (): Locator => page.getByTestId("panel");
const requirement = (text: string): Locator => panel().getByTestId("requirement").filter({ hasText: text });

async function openTab(tab: string): Promise<void> {
  await panel().getByRole("tab", { name: tab }).click();
  await expect(panel().getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
}

async function addRequirement(text: string, test_: string, runs: string, after?: string): Promise<void> {
  await panel().getByRole("button", { name: "Add requirement" }).click();
  const form = panel().getByTestId("add-requirement");
  await form.getByLabel("What must be true").fill(text);
  await form.getByLabel("What a person will see when it is met").fill(test_);
  await form.getByLabel("Estimate, in runs (optional)").fill(runs);
  if (after) await form.getByRole("group", { name: "Must come after" }).getByLabel(new RegExp(after)).check();
  await form.getByRole("button", { name: "Add requirement" }).click();
  await expect(form).toHaveCount(0);
}

test("the Plan opens from the command palette and says what to do when it is empty", async () => {
  await createProject(page, "Plan project");
  await page.keyboard.press("Control+k");
  await page.getByRole("dialog", { name: "Command palette" }).getByRole("textbox").fill("open plan");
  await page.keyboard.press("Enter");
  await expect(panel().getByRole("heading", { name: "Plan" })).toBeFocused();
  await expect(panel()).toContainText("No requirements yet.");
  await expect(panel()).toContainText("Add the first one below");

  // Arrow keys move between the tabs.
  await panel().getByRole("tab", { name: "Scope" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(panel().getByRole("tab", { name: "Dates and budget" })).toBeFocused();
  await expect(panel()).toContainText("No target date.");
  await openTab("Scope");
});

test("the chairman adds two requirements; the second waits on the first, and the longest chain names both", async () => {
  await addRequirement(FIRST, "A reader counts three numbered steps in plan.md.", "2");
  const first = requirement(FIRST);
  await expect(first).toHaveCount(1);
  await expect(first).toContainText("Written by you");
  await expect(first.getByTestId("requirement-estimate")).toContainText("Estimate: 2 runs");
  const firstId = Number(await first.getAttribute("data-requirement-id"));

  await addRequirement(SECOND, "A reader finds a name beside every step.", "3", FIRST);
  const second = requirement(SECOND);
  await expect(second).toHaveCount(1);
  const secondId = Number(await second.getAttribute("data-requirement-id"));
  await expect(second.getByTestId("requirement-depends")).toHaveText(`Depends on requirement ${firstId}`);
  await expect(second.getByTestId("requirement-ready")).toHaveText(/^Not ready: .+/);
  await expect(second.getByTestId("requirement-ready")).toContainText(String(firstId));

  const chain = panel().getByTestId("longest-chain");
  await expect(chain.getByRole("listitem")).toHaveText([`Requirement ${firstId}`, `Requirement ${secondId}`]);
  await expect(chain.getByTestId("chain-runs")).toContainText("5 runs");
});

test("a target date is shown beside the projection", async () => {
  await openTab("Dates and budget");
  await expect(panel().getByTestId("projection-text")).not.toBeEmpty();
  const target = panel().getByTestId("target");
  await target.getByRole("button", { name: "Set a target date" }).click();
  await target.getByLabel("Target date").fill("2031-05-20");
  await target.getByLabel("Where does this date come from?").fill("The launch day.");
  await target.getByRole("button", { name: "Save target date" }).click();
  await expect(target.getByTestId("target-date")).toContainText("2031");
  await expect(target).toContainText("Where it comes from: The launch day.");
  await expect(target.getByTestId("target-beside")).toContainText("the projection is");
});

test("the Plan tabs have no WCAG 2 A or AA violations in both themes (NFR-18)", async () => {
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    for (const [tab, testId] of [
      ["Scope", "requirement"],
      ["Dates and budget", "target-beside"],
      ["Finish", "speed"],
    ] as const) {
      await openTab(tab);
      await expect(panel().getByTestId(testId).first()).toBeVisible();
      await expectNoViolations(page, `Plan ${tab}, ${theme} theme`);
    }
  }
  await setTheme(page, "light");
  await openTab("Scope");
  await panel().getByRole("button", { name: "Add requirement" }).click();
  await expect(panel().getByTestId("add-requirement")).toBeVisible();
  await expectNoViolations(page, "Plan add requirement form");
  await panel().getByTestId("add-requirement").getByRole("button", { name: "Cancel" }).click();
});

test("the chairman cuts a requirement with a reason, and can reopen it", async () => {
  const second = requirement(SECOND);
  await second.getByRole("button", { name: /^Cut/ }).click();
  // Cutting asks for a reason first, and Cancel leaves the requirement as it was.
  await second.getByRole("button", { name: "Cancel" }).click();
  await expect(second.getByTestId("state-tag")).not.toHaveText("State: cut");
  await second.getByRole("button", { name: /^Cut/ }).click();
  await second.getByLabel("Why are you cutting it? Work on it stops.").fill(CUT_REASON);
  await second.getByRole("button", { name: "Cut this requirement" }).click();
  await expect(second.getByTestId("state-tag")).toHaveText("State: cut");
  await expect(second).toContainText(`Reason: ${CUT_REASON}`);
  await expect(second.getByRole("button", { name: /^Cut/ })).toHaveCount(0);
  await expect(second.getByRole("button", { name: /^Reopen/ })).toBeVisible();
  // The cut requirement leaves the longest chain.
  await expect(panel().getByTestId("longest-chain")).not.toContainText(`Requirement ${await second.getAttribute("data-requirement-id")}`);
});
