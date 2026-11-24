/**
 * End-to-end test of drafting a project with the Founder against a real Nightsquad server with the
 * mock model (FND-1, FND-3, FND-5, FND-11, FND-13, RHS-4): the chairman says what they want, sees
 * the draft, its grade and the ledger, answers the first question with the recommended answer, has
 * the Founder use its recommendations for the rest, creates the project once the draft is rehearsed
 * and ready, and starts it. Then the project is rehearsed from the Plan panel, exported and cloned.
 * It runs after desk.spec.ts (one worker, files in name order) and reuses the signed-in session.
 *
 * The Founder's script is one list of turns played through the whole conversation. Who pays is
 * settled without a question because the chairman has exactly one model credential.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { STATE_FILE, expectAccessible, expectNoViolations, setFounderScript, openPanel } from "./helpers";

test.describe.configure({ mode: "serial" });

const SLOW = 45_000;
const acceptance = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "acceptance");
const GOAL = readFileSync(join(acceptance, "reference-goal.md"), "utf8");
const GRADES = (JSON.parse(readFileSync(join(acceptance, "reference-goal.grades.json"), "utf8")) as { grades: unknown[] }).grades;

const NAME = "Hollin Valley bird guide";
const BRIEF = "I want a printed field guide to the birds of the Hollin Valley.";
const DECISIONS = [
  "finish_line",
  "beneficiary_standard",
  "project_type",
  "who_pays",
  "outside_date",
  "budget",
  "anti_metrics",
  "chairman_role",
  "roster",
  "quality",
  "authority_preset",
  "failure_deliverable",
  "resource_posture",
];

const tool = (name: string, args: Record<string, unknown> = {}): unknown => ({ tools: [{ name, arguments: args }] });
const question = (settles: string, text: string, options: string[], changes: string): unknown =>
  tool("ask", { questions: [{ settles, text, options, recommended: 0, changes }] });

const FIRST_QUESTION = "Shall the printer's signed proof be the record that shows the guide is finished?";
const SECOND_QUESTION = "Is the guide for a first-time walker, judged against a published regional guide?";
const SCRIPT = [
  tool("propose_spec", {
    spec: {
      name: NAME,
      goal: GOAL,
      type: "deliver",
      teams: [
        { name: "Entries", role: "researcher", members: ["Rey", "Sol"] },
        { name: "Plan review", role: "plan-adversary", members: ["Ada"] },
      ],
    },
    decisions: Object.fromEntries(DECISIONS.map((key) => [key, { value: `The Founder's recommendation for ${key}.` }])),
    first_requirement: {
      text: "A first usable guide to five birds exists.",
      success_test: "A walker can name each of the five birds from its entry.",
    },
  }),
  question("finish_line", FIRST_QUESTION, ["Yes, the signed proof", "No, something else"], "What counts as finished."),
  { text: "Here is a first draft. I have one question at a time for you." },
  question("beneficiary_standard", SECOND_QUESTION, ["Yes", "No, someone else"], "Who every entry is written for."),
  { text: "Thank you. The finish line is settled. Next: who the guide is for.", word_delay_ms: 120 },
  tool("rehearse_spec"),
  { text: "The draft is rehearsed and ready for you to confirm." },
];

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ storageState: STATE_FILE, acceptDownloads: true })).newPage();
  setFounderScript(SCRIPT, GRADES);
  const added = await page.request.post("/v1/credentials/add", {
    data: { name: "main", provider: "mock", key: "sk-main-0123456789" },
  });
  expect(added.ok(), await added.text()).toBe(true);
});

test.afterAll(async () => {
  await page.context().close();
});

const card = (): Locator => page.getByTestId("question-card");
const ledgerLine = (settles: string): Locator => page.locator(`[data-testid="ledger-line"][data-settles="${settles}"]`);
const readiness = (): Locator => page.getByTestId("readiness");
const panel = (): Locator => page.getByTestId("panel");

test("the project list offers talking first, and the start page is accessible", async () => {
  await page.goto("/projects");
  await expect(page.getByRole("button", { name: "Fill in a form instead" })).toBeVisible();
  await page.getByRole("link", { name: "Start a project" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Start a project" })).toBeVisible();
  await expect(page.getByLabel("What do you want done?")).toBeFocused();
  await expect(page.getByLabel("Attach a document (optional)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Decide everything for me and start" })).toBeVisible();
  await expectAccessible(page, "start a project");
});

test("a short brief gets a draft, its grade, a ledger and one question with a recommended answer (FND-3)", async () => {
  await page.getByLabel("What do you want done?").fill(BRIEF);
  await page.getByRole("button", { name: "Start drafting" }).click();
  await expect(page).toHaveURL(/\/draft\/[0-9a-f]+$/);
  await expect(page.getByTestId("line-person")).toContainText(BRIEF);

  await expect(page.getByTestId("draft-heading")).toHaveText(NAME, { timeout: SLOW });
  await expect(page.getByTestId("draft-name")).toHaveText(NAME);
  await expect(page.getByTestId("draft-team")).toHaveText(["Entries (researcher): Rey, Sol", "Plan review (plan-adversary): Ada"]);
  await expect(page.getByTestId("draft")).toContainText("THE FINISH LINE is the printer's signed proof");
  await expect(page.getByTestId("grade-summary")).toHaveText("Ready: all ten elements are present.");
  await expect(page.locator('[data-testid="grade-element"][data-grade="present"]')).toHaveCount(10);
  await expect(ledgerLine("who_pays")).toContainText("main");
  await expect(ledgerLine("who_pays")).toContainText("assumed");
  await expect(page.getByTestId("draft-rehearsal")).toContainText("This draft has not been rehearsed yet.");

  await expect(card()).toHaveCount(1);
  await expect(card()).toContainText(FIRST_QUESTION);
  await expect(card().getByTestId("question-changes")).toHaveText("What this changes: What counts as finished.");
  const recommended = card().getByRole("button", { name: /^a\. Yes, the signed proof\s*Recommended$/ });
  await expect(recommended).toBeFocused();
  await expect(card().getByRole("button", { name: "b. No, something else" })).toBeVisible();
  // The open question is shown as its card, not also as a line of the conversation.
  await expect(page.getByTestId("line-founder")).toHaveText([/Here is a first draft\./]);

  await expect(readiness()).toHaveAttribute("data-stage", "you");
  await expect(readiness()).toContainText("1 question is waiting for your answer.");
  await expect(readiness()).toContainText("This draft has not been rehearsed.");
  await expect(page.getByRole("button", { name: "Create the project" })).toHaveCount(0);
  await expectAccessible(page, "drafting with an open question");
  await recommended.focus();
});

test("the unfinished draft is listed on the project list and can be gone on with (FND-1)", async () => {
  const draftUrl = page.url();
  await page.goto("/");
  const unfinished = page.getByTestId("unfinished");
  await expect(unfinished).toContainText(BRIEF);
  await expectNoViolations(page, "project list with an unfinished draft");
  await unfinished.getByRole("link", { name: /^Go on/ }).click();
  await expect(page).toHaveURL(draftUrl);
  await expect(card()).toContainText(FIRST_QUESTION);
});

test("Enter on the card accepts the recommendation; the Founder's reply streams in and asks the next question", async () => {
  await expect(card().locator('[data-recommended="true"]')).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(ledgerLine("finish_line")).toContainText("Yes, the signed proof");
  await expect(ledgerLine("finish_line")).toContainText("your answer");
  // The words arrive a few at a time before the finished line is stored.
  await expect(page.getByTestId("founder-reply")).toContainText("Thank you.", { timeout: SLOW });
  await expect(page.getByTestId("line-founder").last()).toContainText("Next: who the guide is for.", { timeout: SLOW });
  await expect(page.getByTestId("founder-reply")).toHaveCount(0);
  await expect(card()).toContainText(SECOND_QUESTION);
  await expect(card().locator('[data-recommended="true"]')).toBeFocused();
});

test("using the recommendations for the rest asks first, records assumptions, and the rehearsed draft becomes ready (FND-5, FND-11)", async () => {
  await page.getByRole("button", { name: "Use your recommendations for the rest" }).click();
  const dialog = page.getByRole("dialog", { name: "Use the Founder's recommendations for the rest?" });
  await expect(dialog).toContainText("recorded as an assumption, not as your answer");
  await expectNoViolations(page, "asking before using the recommendations");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(card()).toHaveCount(1);

  await page.getByRole("button", { name: "Use your recommendations for the rest" }).click();
  await dialog.getByRole("button", { name: "Yes, use its recommendations" }).click();
  await expect(card()).toHaveCount(0);
  await expect(ledgerLine("beneficiary_standard")).toContainText("assumed");

  // The Founder rehearses the draft: a real rehearsal, about 5 seconds.
  await expect(readiness()).toHaveAttribute("data-stage", "ready", { timeout: SLOW });
  await expect(page.getByTestId("draft-rehearsal")).toContainText("Runs to its first verified close.");
  await expect(page.getByTestId("ledger-line")).toHaveCount(DECISIONS.length);
  await expect(ledgerLine("finish_line")).toHaveAttribute("data-source", "answer");
  await expect(ledgerLine("budget")).toHaveAttribute("data-source", "assumption");
  await expect(page.getByRole("button", { name: "Use your recommendations for the rest" })).toHaveCount(0);
  await expectAccessible(page, "a draft that is ready");
});

test("creating the project shows what is still missing and offers to start it; starting lands on the project (FND-13)", async () => {
  await page.getByRole("button", { name: "Create the project" }).click();
  const created = page.getByTestId("created");
  await expect(created.getByRole("heading", { name: `“${NAME}” is created.` })).toBeFocused();
  await expect(created.getByTestId("nothing-missing")).toBeVisible();
  await expect(page.getByLabel("Message to the Founder")).toHaveCount(0);
  await expectNoViolations(page, "a created project, before starting");

  await created.getByRole("button", { name: "Start the project" }).click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f]+\?squad=hired$/);
  // The squad assembles once, then the person meets it on the Squad tab.
  const assembled = page.getByRole("dialog", { name: "Your squad is ready" });
  await expect(assembled).toBeVisible();
  await expectNoViolations(page, "the squad assembled");
  await assembled.getByRole("button", { name: "Meet the squad" }).click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f]+\/squad$/);
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1, name: NAME })).toBeVisible();
  await expect(page.getByTestId("project-state")).toHaveAttribute("data-state", "running");
  // The drafting conversation became the project chat.
  await expect(page.getByRole("log", { name: "Messages" })).toContainText(`You: ${BRIEF}`);

  await page.goto("/");
  await expect(page.locator("#content").getByRole("link", { name: new RegExp(NAME) })).toBeVisible();
  await expect(page.getByTestId("unfinished")).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1, name: NAME })).toBeVisible();
});

test("the Plan panel rehearses the project and shows the report in sections (RHS-3, RHS-4)", async () => {
  await openPanel(page, "Plan");
  await panel().getByRole("tab", { name: "Rehearsal" }).click();
  await panel().getByRole("button", { name: "Rehearse", exact: true }).click();
  await expect(panel().getByTestId("rehearsing")).toHaveText("Rehearsing. This takes about 5 seconds.");
  await expect(panel().getByTestId("rehearsal-verdict")).toContainText("Runs to its first verified close.", { timeout: SLOW });
  await expect(panel().getByTestId("rehearsal-walk").getByRole("listitem").first()).toContainText("Roles resolve");
  for (const title of ["The walk", "Times it waited for you", "Setup still missing", "Rules hit", "What the rehearsal could not try"]) {
    await expect(panel().getByRole("heading", { name: title })).toBeVisible();
  }
  await expect(panel()).toContainText("It does not predict how good the work will be.");
  await expect(panel().getByRole("button", { name: "Rehearse again" })).toBeEnabled();
  await expectAccessible(page, "rehearsal report");
});

test("the project is exported as a spec file and cloned into a new project", async () => {
  await openPanel(page, "Settings");
  const copies = panel().getByTestId("project-copies");
  const download = page.waitForEvent("download");
  await copies.getByRole("button", { name: "Export as a spec" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("hollin-valley-bird-guide.spec.json");
  const spec = JSON.parse(readFileSync(await file.path(), "utf8")) as { name: string; goal: string; paying_credential: string };
  expect([spec.name, spec.goal, spec.paying_credential]).toEqual([NAME, GOAL, "main"]);
  await expect(copies.getByTestId("spec-saved")).toHaveText("Saved as hollin-valley-bird-guide.spec.json.");

  await copies.getByRole("button", { name: "Clone", exact: true }).click();
  const name = copies.getByLabel("Name of the new project");
  await expect(name).toHaveValue(`Copy of ${NAME}`);
  await expectNoViolations(page, "settings with the clone form");
  await name.fill("Second bird guide");
  await copies.getByRole("button", { name: "Clone and open" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Second bird guide" })).toBeVisible();
  await expect(page.getByTestId("project-state")).toHaveAttribute("data-state", "draft");
});
