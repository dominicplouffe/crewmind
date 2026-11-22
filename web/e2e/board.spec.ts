/**
 * End-to-end tests of the Board panel against a real crewmind server with the mock model: tasks and
 * their check labels, audit samples, outside evidence and launches.
 * It runs after app.spec.ts (one worker, files in name order) and reuses its signed-in session.
 *
 * Only agents create tasks, so the mock CEO and Reviewer are scripted (`CEO.work.json`,
 * `Reviewer.work.json`) and the chairman's `/do` directive starts each CEO work run.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  IDLE_SCRIPT,
  STATE_FILE,
  createProject,
  expectNoViolations,
  setTheme,
  setWorkScript,
  toolTurn,
} from "./helpers";

test.describe.configure({ mode: "serial" });

const SLOW = 60_000;
const DRAFT = "Draft the plan";
const VENUE = "Book the venue";
const EVIDENCE = "plan.md now has three numbered steps.";
const REVIEW_NOTES = "I read plan.md and counted three numbered steps.";
const BLOCK_REASON = "The venue has not answered our email.";
const LAUNCH = "Publish the plan on the public site.";
const MAIL = "Email the venue to ask for dates.";

interface TaskRow {
  id: number;
  title: string;
  state: string;
  label: string;
}

let page: Page;
let projectId = "";
let draftId = 0;
let venueId = 0;

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ storageState: STATE_FILE })).newPage();
  setWorkScript("CEO", IDLE_SCRIPT);
  setWorkScript("Reviewer", IDLE_SCRIPT);
});

test.afterAll(async () => {
  setWorkScript("CEO", IDLE_SCRIPT);
  setWorkScript("Reviewer", IDLE_SCRIPT);
  await page.context().close();
});

const panel = (): Locator => page.getByTestId("panel");
const taskRow = (id: number): Locator => panel().locator(`[data-testid="task"][data-task-id="${id}"]`);
const group = (state: string): Locator => panel().locator(`[data-testid="task-group"][data-state="${state}"]`);

async function openBoard(tab: string): Promise<void> {
  if (!(await panel().getByRole("tab", { name: tab }).isVisible())) {
    await page.getByRole("button", { name: "Board", exact: true }).click();
  }
  await panel().getByRole("tab", { name: tab }).click();
  await expect(panel().getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
}

async function tasks(): Promise<TaskRow[]> {
  const response = await page.request.get(`/v1/tasks/list?project_id=${projectId}`);
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { items: TaskRow[] }).items;
}

/** The chairman's directive: it starts a work run of the CEO. */
async function direct(text: string): Promise<void> {
  const response = await page.request.post("/v1/chat/command", { data: { project_id: projectId, text: `/do ${text}` } });
  expect(response.ok(), await response.text()).toBe(true);
}

async function stateOf(id: number): Promise<string | undefined> {
  return (await tasks()).find((task) => task.id === id)?.state;
}

test("the Board opens from the command palette and its empty states say agents create the work", async () => {
  await createProject(page, "Board project");
  projectId = new URL(page.url()).pathname.split("/").pop() ?? "";
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByTestId("project-state")).toHaveText("running");

  await page.keyboard.press("Control+k");
  await page.getByRole("dialog", { name: "Command palette" }).getByRole("textbox").fill("board");
  await page.keyboard.press("Enter");
  await expect(panel().getByRole("heading", { name: "Board" })).toBeFocused();
  await expect(panel()).toContainText("No tasks yet.");
  await expect(panel()).toContainText("Agents create tasks, not people.");

  // Arrow keys move between the tabs.
  await panel().getByRole("tab", { name: "Tasks" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(panel().getByRole("tab", { name: "Audit" })).toBeFocused();
  await expect(panel()).toContainText("Nothing to audit yet.");
  await expect(panel()).toContainText("Agents create and close tasks, not people.");
  await openBoard("Evidence");
  await expect(panel()).toContainText("No outside evidence yet.");
  await expect(panel()).toContainText("Agents file evidence, not people.");
  await openBoard("Launches");
  await expect(panel()).toContainText("No side effects or launches yet.");
  await expect(panel()).toContainText("Agents declare these, not people.");
  await openBoard("Tasks");
});

test("tasks the CEO creates appear as ready, not yet checked, without a reload", async () => {
  test.setTimeout(120_000);
  const settings = await page.request.post("/v1/settings/change_project", {
    data: { project_id: projectId, changes: { "audit.sample_rate": 100 }, reason: "Audit every close in this test." },
  });
  expect(settings.ok(), await settings.text()).toBe(true);

  const task = (title: string, goal: string, success_test: string): [string, Record<string, unknown>] => [
    "agent_create_task",
    { title, goal, success_test, test_kind: "observable" },
  ];
  setWorkScript("CEO", [
    toolTurn(
      task(DRAFT, "Write the first draft of the plan.", "A reader finds three numbered steps in plan.md."),
      task(VENUE, "Find and book a venue for the launch.", "A reader sees a booking confirmation in venue.md."),
    ),
    { text: "Planned." },
  ]);
  await direct("Plan the work.");
  await expect.poll(async () => (await tasks()).map((item) => item.title), { timeout: SLOW, intervals: [250] }).toEqual(
    expect.arrayContaining([DRAFT, VENUE]),
  );
  // The new tasks wake the CEO again: it must not create them a second time.
  setWorkScript("CEO", IDLE_SCRIPT);
  const created = await tasks();
  draftId = created.find((item) => item.title === DRAFT)?.id ?? 0;
  venueId = created.find((item) => item.title === VENUE)?.id ?? 0;
  expect(draftId).toBeGreaterThan(0);
  expect(venueId).toBeGreaterThan(0);

  // The panel was open and empty: the live stream's change event fills it.
  const row = group("ready").locator(`[data-task-id="${draftId}"]`);
  await expect(row).toBeVisible({ timeout: SLOW });
  await expect(row.getByRole("button", { name: DRAFT })).toBeVisible();
  await expect(row.getByTestId("state-tag")).toHaveText("State: ready");
  await expect(row.getByTestId("check-label")).toHaveText("Check: not yet checked");
  await expect(group("ready").locator(`[data-task-id="${venueId}"]`)).toBeVisible();
  await expect(panel().getByRole("heading", { name: /^ready \(\d+\)$/ })).toBeVisible();
});

test("a claimed task moves to the claimed group and names who holds it", async () => {
  test.setTimeout(120_000);
  setWorkScript("CEO", [toolTurn(["agent_claim_task", { task_id: draftId }]), { text: "Claimed." }]);
  await direct("Claim the draft.");
  const row = group("claimed").locator(`[data-task-id="${draftId}"]`);
  await expect(row).toBeVisible({ timeout: SLOW });
  await expect(row).toContainText("Held by CEO");
  await expect(row.getByTestId("check-label")).toHaveText("Check: not yet checked");
  // Claimed work is listed before ready work.
  await expect(panel().getByTestId("task-group").first()).toHaveAttribute("data-state", "claimed");
});

test("a reviewed task closes as done with the label reviewed, never verified", async () => {
  test.setTimeout(180_000);
  setWorkScript("Reviewer", [
    toolTurn(["agent_review_task", { task_id: draftId, ok: true, notes: REVIEW_NOTES }]),
    { text: "Reviewed." },
  ]);
  setWorkScript("CEO", [
    toolTurn(
      ["agent_complete_task", { task_id: draftId, evidence: EVIDENCE }],
      ["agent_claim_task", { task_id: venueId }],
      ["agent_block_task", { task_id: venueId, reason: BLOCK_REASON }],
      [
        "agent_declare_effect",
        { key: "site-live", what: LAUNCH, launch: true, watch: { kind: "command", check: "test -f up.txt", interval_minutes: 15 } },
      ],
      ["agent_finish_effect", { key: "site-live", fired: true, outcome: "The plan is on the site." }],
      ["agent_declare_effect", { key: "mail-venue", what: MAIL }],
      ["agent_finish_effect", { key: "mail-venue", fired: true, outcome: "The email was sent." }],
    ),
    { text: "Done." },
  ]);
  await direct("Finish the draft and chase the venue.");
  // The CEO completes it (review), then the Reviewer is woken and passes it (done).
  await expect.poll(() => stateOf(draftId), { timeout: SLOW }).toMatch(/^(review|done)$/);
  await expect.poll(() => stateOf(draftId), { timeout: SLOW }).toBe("done");
  setWorkScript("CEO", IDLE_SCRIPT);
  setWorkScript("Reviewer", IDLE_SCRIPT);

  // Closed tasks are folded away.
  const toggle = panel().getByRole("button", { name: /^Show closed tasks \(\d+\)$/ });
  await expect(toggle).toBeVisible({ timeout: SLOW });
  await expect(taskRow(draftId)).toHaveCount(0);
  await toggle.click();
  const row = group("done").locator(`[data-task-id="${draftId}"]`);
  await expect(row).toBeVisible();
  await expect(row.getByTestId("check-label")).toHaveText("Check: reviewed");
  await expect(row).not.toContainText("verified");
  await expect(row).not.toContainText("✓");

  await row.getByRole("button", { name: DRAFT }).click();
  const detail = panel().getByTestId("task-detail");
  await expect(detail.getByRole("heading", { name: `Task ${draftId}: ${DRAFT}` })).toBeFocused();
  await expect(detail.getByTestId("who-checked")).toHaveText("Who checked it: An independent reviewer read it and passed it.");
  await expect(detail.getByTestId("check-label")).toHaveText("Check: reviewed");
  await expect(detail).toContainText("Write the first draft of the plan.");
  await expect(detail).toContainText("A reader finds three numbered steps in plan.md.");
  await expect(detail.getByTestId("test-kind")).toHaveText("Something a reviewer reads.");
  await expect(detail.getByTestId("task-evidence")).toHaveText(EVIDENCE);
  const attempt = detail.getByTestId("attempt");
  await expect(attempt).toHaveCount(1);
  await expect(attempt).toContainText("Attempt 1 by CEO");
  await expect(attempt).toContainText(EVIDENCE);
  await expect(attempt.getByTestId("attempt-result")).toHaveText("Result: passed");
  await expect(attempt.locator("pre")).toHaveText(REVIEW_NOTES);
  await expect(detail).not.toContainText("verified");
});

test("a blocked task shows its reason, and “Open only” leaves closed tasks out", async () => {
  await panel().getByRole("button", { name: "Back to tasks" }).click();
  const row = group("blocked").locator(`[data-task-id="${venueId}"]`);
  await expect(row).toBeVisible({ timeout: SLOW });

  await panel().getByLabel("Open only").check();
  await expect(panel().getByRole("button", { name: /closed tasks/ })).toHaveCount(0);
  await expect(taskRow(draftId)).toHaveCount(0);
  await expect(row).toBeVisible();

  await row.getByRole("button", { name: VENUE }).click();
  const detail = panel().getByTestId("task-detail");
  await expect(detail.getByTestId("state-tag")).toHaveText("State: blocked");
  await expect(detail.getByTestId("task-reason")).toContainText(BLOCK_REASON);
  // An open task makes no claim about who checked it.
  await expect(detail.getByTestId("who-checked")).toHaveCount(0);
  await expect(detail).toContainText("No attempts yet.");
  await panel().getByRole("button", { name: "Back to tasks" }).click();
  await panel().getByLabel("Open only").uncheck();
  await expect(panel().getByRole("button", { name: /closed tasks/ })).toBeVisible();
});

test("the chairman fails an audit sample with a note, and it then shows failed", async () => {
  await openBoard("Audit");
  await expect(panel().getByTestId("audit-drawn")).toHaveText("1 of 1 close was drawn for you.");
  const sample = panel().getByTestId("audit").filter({ hasText: DRAFT });
  await expect(sample).toHaveCount(1);
  await expect(sample.getByTestId("check-label")).toHaveText("Check: reviewed");
  await expect(sample).toContainText(EVIDENCE);
  await expect(sample.getByTestId("audit-verdict")).toHaveText("Your verdict: waiting for you");

  await sample.getByRole("button", { name: /^Fail/ }).click();
  await sample.getByLabel("What you found (optional)").fill("The plan has two steps, not three.");
  await sample.getByRole("button", { name: "Record as failed" }).click();
  await expect(sample.getByTestId("audit-verdict")).toHaveText("Your verdict: failed");
  await expect(sample.getByRole("button", { name: /^(Pass|Fail)/ })).toHaveCount(0);
});

test("a launch shows its watch, a failing watch is a status line, and the chairman retires it", async () => {
  test.setTimeout(180_000);
  await openBoard("Launches");
  const launch = panel().getByTestId("launch").filter({ hasText: LAUNCH });
  await expect(launch).toHaveCount(1);
  await expect(launch.getByTestId("launch-kind")).toHaveText("Launch");
  await expect(launch.getByTestId("state-tag")).toHaveText("State: finished");
  await expect(launch.getByTestId("launch-watch")).toHaveText(/^Watch: (passing|failing)$/);
  await expect(launch).toContainText("The plan is on the site.");

  // A plain side effect has no watch and cannot be retired.
  const mail = panel().getByTestId("launch").filter({ hasText: MAIL });
  await expect(mail.getByTestId("launch-kind")).toHaveText("Side effect");
  await expect(mail.getByTestId("launch-watch")).toHaveCount(0);
  await expect(mail.getByRole("button", { name: /Retire/ })).toHaveCount(0);

  // The watch command fails (there is no up.txt): the server says so in the chat and on the launch.
  await expect(page.getByTestId("message-platform").filter({ hasText: "A watch is failing" }).first()).toBeVisible({
    timeout: SLOW,
  });
  await panel().getByRole("button", { name: "Refresh" }).click();
  await expect(launch.getByTestId("launch-watch")).toHaveText("Watch: failing");
  await expect(launch.locator("pre")).toContainText("exit 1");

  await launch.getByRole("button", { name: /^Retire/ }).click();
  await expect(launch).toContainText("Retire this launch? Its watch ends, and it cannot be brought back.");
  await launch.getByRole("button", { name: "Cancel" }).click();
  await expect(launch.getByTestId("state-tag")).toHaveText("State: finished");
  await launch.getByRole("button", { name: /^Retire/ }).click();
  await launch.getByRole("button", { name: "Yes, retire it" }).click();
  await expect(launch.getByTestId("state-tag")).toHaveText("State: retired");
  await expect(launch.getByTestId("launch-watch")).toHaveText("Watch: ended");
  await expect(launch.getByRole("button", { name: /Retire/ })).toHaveCount(0);
});

test("every Board tab has no WCAG 2 A or AA violations in both themes (NFR-18)", async () => {
  test.setTimeout(180_000);
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await openBoard("Tasks");
    // The fold closes again each time the tab is opened.
    const toggle = panel().getByRole("button", { name: /closed tasks/ });
    await expect(toggle).toBeVisible();
    if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
    await expect(taskRow(draftId)).toBeVisible();
    await expectNoViolations(page, `Board tasks, ${theme} theme`);
    await taskRow(draftId).getByRole("button", { name: DRAFT }).click();
    await expect(panel().getByTestId("attempt")).toBeVisible();
    await expectNoViolations(page, `Board task detail, ${theme} theme`);
    await panel().getByRole("button", { name: "Back to tasks" }).click();
    for (const [tab, testId] of [
      ["Audit", "audit"],
      ["Launches", "launch"],
    ] as const) {
      await openBoard(tab);
      await expect(panel().getByTestId(testId).first()).toBeVisible();
      await expectNoViolations(page, `Board ${tab}, ${theme} theme`);
    }
    await openBoard("Evidence");
    await expect(panel()).toContainText("No outside evidence yet.");
    await expectNoViolations(page, `Board Evidence, ${theme} theme`);
  }
  await setTheme(page, "light");
});
