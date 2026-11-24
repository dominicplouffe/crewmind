/**
 * End-to-end tests of "listening" against a real Nightsquad server with the mock model: standing orders,
 * decisions, corrections, examples, memory, the listening score and history paging.
 * Covers CHAT-8, CHAT-11 to CHAT-13, MSG-4 to MSG-7, MEM-1, MEM-3, MEM-6, NFR-18.
 * It runs after app.spec.ts (one worker, files in name order) and reuses its signed-in session.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  agentName,
  PLAN_SCRIPT,
  STATE_FILE,
  createProject,
  expectAccessible,
  expectNoViolations,
  sendMessage,
  setCeoScript,
  setTheme, openPanel } from "./helpers";

test.describe.configure({ mode: "serial" });

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ storageState: STATE_FILE })).newPage();
  setCeoScript(PLAN_SCRIPT);
});

test.afterAll(async () => {
  setCeoScript(PLAN_SCRIPT);
  await page.context().close();
});

const panel = (): Locator => page.getByTestId("panel");
const personMessage = (text: string): Locator => page.getByTestId("message-person").filter({ hasText: text });
const agentMessages = (): Locator => page.getByTestId("message-agent");
const statusLine = (text: string | RegExp): Locator => page.getByTestId("message-platform").filter({ hasText: text });

async function openMemory(tab: string): Promise<void> {
  if (!(await panel().getByRole("tab", { name: tab }).isVisible())) {
    await openPanel(page, "Memory");
  }
  await panel().getByRole("tab", { name: tab }).click();
  await expect(panel().getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
}

async function chooseAction(message: Locator, action: string): Promise<void> {
  await message.getByRole("button", { name: /^More/ }).click();
  await message.getByRole("menuitem", { name: action }).click();
}

/** Sends a message and waits for the mock CEO's reply to it. */
async function ask(text: string, reply: string | RegExp): Promise<Locator> {
  const before = await agentMessages().count();
  await sendMessage(page, text);
  await expect(agentMessages()).toHaveCount(before + 1, { timeout: 30_000 });
  await expect(agentMessages().last()).toContainText(reply);
  return page.locator(`#${await agentMessages().last().getAttribute("id")}`);
}

test("the Memory panel opens from the command palette and says what will fill it", async () => {
  await createProject(page, "Listening project");
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByTestId("project-state")).toHaveAttribute("data-state", "running");

  await page.keyboard.press("Control+k");
  await page.getByRole("dialog", { name: "Command palette" }).getByRole("combobox").fill("memory");
  await page.keyboard.press("Enter");
  await expect(panel().getByRole("heading", { name: "Memory" })).toBeFocused();
  await expect(panel().getByTestId("pinned-text")).toContainText("Write a short plan.");
  await expect(panel().getByTestId("listening-score")).toHaveText("Listening: no replies yet");

  // Arrow keys move between the tabs.
  await panel().getByRole("tab", { name: "Pinned" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(panel().getByRole("tab", { name: "Standing orders" })).toBeFocused();
  await expect(panel()).toContainText("No standing orders yet.");
  await expect(panel()).toContainText("Pin as a standing order");
  await openMemory("Decisions");
  await expect(panel()).toContainText("No decisions yet.");
  await openMemory("Corrections");
  await expect(panel()).toContainText("No corrections yet.");
  await openMemory("Your preferences");
  await expect(panel().getByRole("textbox", { name: "A preference, in your own words" })).toBeVisible();
});

test("pin a typed order in the Memory panel and see it in the pinned text (MSG-4, MEM-1)", async () => {
  await openMemory("Standing orders");
  await panel().getByLabel("New standing order, in one sentence").fill("Use metric units.");
  await panel().getByRole("button", { name: "Pin order" }).click();
  const order = panel().getByTestId("order").filter({ hasText: "Use metric units." });
  await expect(order).toContainText("In force");
  await expect(order).toContainText("From Admin");
  await expect(statusLine("Standing order 1: Use metric units.")).toBeVisible();

  await openMemory("Pinned");
  await expect(panel().getByTestId("pinned-text")).toContainText("Use metric units.");
  const meters = panel().getByTestId("meter");
  await expect(meters.nth(0)).toContainText(/Project: [\d,]+ of [\d,]+ tokens/);
  await expect(meters.nth(1)).toContainText(/Agent: [\d,]+ of [\d,]+ tokens/);
  await expect(panel().getByLabel("Agent", { exact: true })).toHaveValue("CEO");
});

test("pin a message with its button, edit the proposed sentence and confirm it (CHAT-8, MSG-4)", async () => {
  await ask("Always write in British English please", "Here is the plan");
  await chooseAction(personMessage("Always write in British English please"), "Pin as a standing order");
  const dialog = page.getByRole("dialog", { name: "Proposed standing order" });
  const sentence = dialog.getByLabel("The order, in one sentence");
  await expect(sentence).toHaveValue("Always write in British English please");
  await expect(dialog).toContainText("It is not in force yet.");
  await sentence.fill("Write in British English.");
  const confirmed = page.waitForRequest((request) => request.url().endsWith("/v1/orders/confirm"));
  await dialog.getByRole("button", { name: "Confirm" }).click();
  expect((await confirmed).postDataJSON()).toMatchObject({ text: "Write in British English." });
  await expect(dialog).toHaveCount(0);
  await expect(statusLine("Standing order 2: Write in British English.")).toBeVisible();

  await openMemory("Standing orders");
  await expect(panel().getByTestId("order").filter({ hasText: "Write in British English." })).toContainText("In force");
});

test("a long message is proposed shortened; discard it, and retire an order (MSG-4)", async () => {
  const long = `Whenever you write for me, ${"keep it short and ".repeat(40)}stop.`;
  await ask(long, "Here is the plan");
  await chooseAction(personMessage("Whenever you write for me"), "Pin as a standing order");
  const dialog = page.getByRole("dialog", { name: "Proposed standing order" });
  await expect(dialog).toContainText("Nightsquad is shortening it");
  await dialog.getByRole("button", { name: "Decide later" }).click();
  await expect(dialog).toHaveCount(0);

  await openMemory("Standing orders");
  const proposed = panel().getByTestId("order").filter({ hasText: "Whenever you write for me" });
  await expect(proposed).toContainText("Proposed, not in force yet");
  await proposed.getByRole("button", { name: /^Discard/ }).click();
  await expect(proposed).toHaveCount(0);

  const metric = panel().getByTestId("order").filter({ hasText: "Use metric units." });
  await metric.getByRole("button", { name: /^Retire/ }).click();
  await expect(metric).toContainText("Retired");
  await expect(metric.getByRole("button")).toHaveCount(0);
});

test("decide, reopen and rule again on a decision (MSG-5)", async () => {
  await openMemory("Decisions");
  await panel().getByLabel("Decision, written as “Topic: ruling”").fill("Database: use Postgres");
  await panel().getByRole("button", { name: "Decide", exact: true }).click();
  const decision = panel().getByTestId("decision").filter({ hasText: "Database" });
  await expect(decision).toContainText("Database: use Postgres");
  await expect(decision).toContainText("Closed");

  await decision.getByRole("button", { name: /^Reopen/ }).click();
  await expect(decision).toContainText("Open again, waiting for your ruling");
  await expect(statusLine("Decision 1 (Database) is open again.")).toBeVisible();
  await decision.getByLabel("New ruling for Database").fill("use SQLite");
  await decision.getByRole("button", { name: "Give ruling" }).click();
  await expect(decision).toContainText("Database: use SQLite");
  await expect(decision).toContainText("Closed");

  // "Decide" on a message opens the form filled with the message's words.
  await chooseAction(personMessage("Always write in British English please"), "Decide");
  const dialog = page.getByRole("dialog", { name: "Close a decision" });
  const text = dialog.getByLabel("Decision, written as “Topic: ruling”");
  await expect(text).toHaveValue("Always write in British English please");
  await text.fill("Language: British English");
  await dialog.getByRole("button", { name: "Decide" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(statusLine("Decision 2 is closed. Language: British English")).toBeVisible();
  await expect(panel().getByTestId("decision").filter({ hasText: "Language" })).toContainText("British English");
});

test("“Not what I asked” records a correction and the agent answers again (CHAT-8, MSG-6, CHAT-13)", async () => {
  const reply = await ask("Make a list of fruit", "Here is the plan");
  setCeoScript([{ text: "Here is the list you asked for." }]);
  await chooseAction(reply, "Not what I asked");
  const dialog = page.getByRole("dialog", { name: "Not what I asked" });
  const ceo = await agentName(page);
  await expect(dialog).toContainText(`${ceo} will answer again and remember this.`);

  // The server refuses empty words, in its own words.
  await dialog.getByRole("button", { name: "Send correction" }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();

  const before = await agentMessages().count();
  await dialog.getByLabel("What you asked for, in your own words").fill("I asked for a list, not a plan");
  const recorded = page.waitForRequest((request) => request.url().endsWith("/v1/corrections/record"));
  await dialog.getByRole("button", { name: "Send correction" }).click();
  const sent = (await recorded).postDataJSON() as { message_id: number };
  expect(`message-${sent.message_id}`).toBe(await reply.getAttribute("id"));
  await expect(dialog).toHaveCount(0);

  await expect(personMessage("Not what I asked: I asked for a list, not a plan")).toBeVisible();
  await expect(agentMessages()).toHaveCount(before + 1, { timeout: 30_000 });
  const again = agentMessages().last();
  await expect(again.locator("blockquote")).toContainText("Make a list of fruit");
  await expect(again).toContainText("Here is the list you asked for.");
  setCeoScript(PLAN_SCRIPT);

  await openMemory("Corrections");
  const correction = panel().getByTestId("correction").filter({ hasText: "I asked for a list, not a plan" });
  await expect(correction).toContainText("Make a list of fruit");
  await expect(correction).toContainText(`To ${ceo}`);
  await expect(correction).toContainText("In force");

  await openMemory("Pinned");
  await expect(panel().getByTestId("listening-score")).toHaveText(/Listening: 1 correction in \d+ repl(y|ies) \(score [\d.,]+\)/);
  await openPanel(page, "Models");
  // Every project has a second agent, the Reviewer: the correction counts against the CEO only.
  const ceoCard = panel().getByRole("listitem").filter({ has: page.getByRole("heading", { name: ceo, exact: true }) });
  await expect(ceoCard.getByTestId("listening-score")).toHaveText(/Listening: 1 correction in \d+ repl(y|ies) \(score [\d.,]+\)/);

  await openMemory("Corrections");
  await correction.getByRole("button", { name: /^Remove/ }).click();
  await expect(correction).toContainText("Removed");
});

test("mark a message as an example with the keyboard, then remove the mark (CHAT-8, MSG-7)", async () => {
  const message = personMessage("Make a list of fruit");
  await message.getByRole("button", { name: /^More/ }).focus();
  await page.keyboard.press("Enter");
  await expect(message.getByRole("menuitem", { name: "Pin as a standing order" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(message.getByRole("menuitem", { name: "Mark as an example" })).toBeFocused();
  const marked = page.waitForResponse((response) => response.url().endsWith("/v1/examples/mark"));
  await page.keyboard.press("Enter");
  expect(await (await marked).json()).toMatchObject({ is_example: true });
  await expect(message.getByTestId("marker-example")).toHaveText("Example");
  await expect(message.getByRole("button", { name: /^More/ })).toBeFocused();

  await chooseAction(message, "Remove example mark");
  await expect(message.getByTestId("marker-example")).toHaveCount(0);
});

test("an agent's proposed order and reopen request get buttons on their status lines (MSG-4, MSG-5)", async () => {
  setCeoScript([
    { tools: [{ name: "agent_propose_order", arguments: { text: "Report every Friday on one page." } }] },
    // The run ends with a reply: a message left unanswered starts another run, which would propose again.
    { text: "I proposed a standing order." },
  ]);
  await sendMessage(page, "How should you report?");
  const ceo = await agentName(page);
  const proposal = statusLine(`${ceo} proposes a standing order`);
  await expect(proposal.getByTestId("order-actions")).toBeVisible({ timeout: 30_000 });
  await expect(agentMessages().last()).toContainText("I proposed a standing order.");
  await expect(proposal.getByRole("button", { name: /^Discard/ })).toBeVisible();
  await proposal.getByRole("button", { name: /^Edit/ }).click();
  const dialog = page.getByRole("dialog", { name: "Proposed standing order" });
  await expect(dialog.getByLabel("The order, in one sentence")).toHaveValue("Report every Friday on one page.");
  await dialog.getByLabel("The order, in one sentence").fill("Report every Friday.");
  await dialog.getByRole("button", { name: "Confirm" }).click();
  await expect(proposal).toContainText("This standing order is now in force.");
  await expect(proposal.getByRole("button", { name: /^Confirm/ })).toHaveCount(0);
  await expect(statusLine(/Standing order \d+: Report every Friday\./)).toBeVisible();

  setCeoScript(PLAN_SCRIPT);
  await ask("We now have a second office that needs SQLite files", "Here is the plan");
  const evidence = (await personMessage("We now have a second office").getAttribute("id"))?.replace("message-", "");
  setCeoScript([
    {
      tools: [
        {
          name: "agent_request_reopen",
          arguments: {
            decision_id: 1,
            reason: "The second office changes what the database must do.",
            evidence: [{ kind: "message", ref: evidence }],
          },
        },
      ],
    },
    { text: "I asked to reopen the decision." },
  ]);
  await sendMessage(page, "Does that change anything?");
  const request = statusLine(`${ceo} asks to reopen decision 1`);
  await expect(request.getByTestId("request-actions")).toBeVisible({ timeout: 30_000 });
  await expect(agentMessages().last()).toContainText("I asked to reopen the decision.");
  setCeoScript(PLAN_SCRIPT);

  await openMemory("Decisions");
  const listed = panel().getByTestId("reopen-request");
  await expect(listed).toContainText(`${ceo} asks to reopen decision 1 (Database)`);
  await expect(listed).toContainText("The second office changes what the database must do.");
  await expect(listed.getByRole("button", { name: /^Decline/ })).toBeVisible();

  await request.getByRole("button", { name: /^Approve/ }).click();
  await expect(request).toContainText("You approved this request.");
  await expect(listed).toContainText("You approved this request.");
  await expect(panel().getByTestId("decision").filter({ hasText: "Database" })).toContainText("Open again");
});

test("add, edit, search, pin and forget a recalled memory (MEM-3, MEM-6)", async () => {
  await openMemory("Recalled memory");
  await panel().getByLabel("A fact to remember").fill("The client prefers teal buttons.");
  await panel().getByRole("button", { name: "Remember" }).click();
  const entries = panel().getByTestId("memory-entry");
  const teal = entries.filter({ hasText: "The client prefers teal buttons." });
  await expect(teal).toContainText("From the chairman");
  await expect(teal).toContainText("project");

  await teal.getByRole("button", { name: /^Edit/ }).click();
  await panel().getByLabel("The fact, corrected").fill("The client prefers green buttons.");
  await panel().getByRole("button", { name: "Save" }).click();
  const green = entries.filter({ hasText: "The client prefers green buttons." });
  await expect(green).toBeVisible();
  await expect(teal).toHaveCount(0);

  await panel().getByRole("searchbox", { name: "Search recalled memory" }).fill("green");
  await panel().getByRole("button", { name: "Search", exact: true }).click();
  await expect(panel().getByTestId("memory-found")).toContainText("found for “green”");
  await expect(green).toBeVisible();
  await panel().getByRole("searchbox", { name: "Search recalled memory" }).fill("zebra");
  await panel().getByRole("searchbox", { name: "Search recalled memory" }).press("Enter");
  await expect(panel().getByTestId("memory-found")).toHaveText("Nothing found for “zebra”. Try another word.");
  await panel().getByRole("button", { name: "Show all" }).click();

  await panel().getByLabel("Show", { exact: true }).selectOption("project");
  await expect(green).toBeVisible();
  await green.getByRole("button", { name: /^Pin/ }).click();
  await expect(panel().getByTestId("server-note")).toContainText("Pinned as a standing order.");
  await expect(statusLine(/Standing order \d+: The client prefers green buttons\./)).toBeVisible();

  await green.getByRole("button", { name: /^Forget/ }).click();
  await expect(green).toContainText("It cannot be brought back.");
  await green.getByRole("button", { name: "Cancel" }).click();
  await expect(green).toBeVisible();
  await green.getByRole("button", { name: /^Forget/ }).click();
  await green.getByRole("button", { name: "Yes, forget it" }).click();
  await expect(green).toHaveCount(0);

  await openMemory("Pinned");
  await expect(panel().getByTestId("pinned-text")).toContainText("The client prefers green buttons.");
});

test("add and forget a preference that applies across projects", async () => {
  await openMemory("Your preferences");
  await expect(panel()).toContainText("No preferences yet.");
  await panel().getByLabel("A preference, in your own words").fill("Keep answers short.");
  await panel().getByRole("button", { name: "Add preference" }).click();
  const entry = panel().getByTestId("memory-entry").filter({ hasText: "Keep answers short." });
  await expect(entry).toBeVisible();
  await expect(entry.getByRole("button", { name: /^Edit/ })).toHaveCount(0);
  await entry.getByRole("button", { name: /^Forget/ }).click();
  await entry.getByRole("button", { name: "Yes, forget it" }).click();
  await expect(entry).toHaveCount(0);
  await expect(panel()).toContainText("No preferences yet.");
});

test("the Memory panel, the message menu and the dialogs are accessible in both themes (NFR-18)", async () => {
  for (const tab of ["Pinned", "Standing orders", "Decisions", "Corrections", "Recalled memory", "Your preferences"]) {
    await openMemory(tab);
    await expect(panel().getByRole("tabpanel")).toBeVisible();
    await expectAccessible(page, `memory panel, ${tab}`);
  }
  await openMemory("Recalled memory");
  await panel().getByLabel("A fact to remember").fill("The office closes at six.");
  await panel().getByRole("button", { name: "Remember" }).click();
  const fact = panel().getByTestId("memory-entry").filter({ hasText: "The office closes at six." });
  await fact.getByRole("button", { name: /^Forget/ }).click();
  await expectAccessible(page, "memory panel, asking before forgetting");
  await page.getByRole("button", { name: "Close panel" }).click();

  // Choosing the theme closes an open menu or dialog, so each theme is set first and then scanned.
  const message = personMessage("Make a list of fruit");
  for (const theme of ["dark", "light"] as const) {
    await setTheme(page, theme);
    await message.getByRole("button", { name: /^More/ }).click();
    await expect(message.getByRole("menu")).toBeVisible();
    await expectNoViolations(page, `message menu, ${theme} theme`);
    await message.getByRole("menuitem", { name: "Decide" }).click();
    await expect(page.getByRole("dialog", { name: "Close a decision" })).toBeVisible();
    await expectNoViolations(page, `decision dialog, ${theme} theme`);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(message.getByRole("button", { name: /^More/ })).toBeFocused();
  }
});

test("earlier messages load a page at a time and the view stays where it was", async () => {
  await createProject(page, "History project");
  const projectId = page.url().split("/").pop() ?? "";
  let lastSent = 0;
  for (let index = 1; index <= 120; index += 1) {
    const sent = await page.request.post("/v1/chat/send", {
      data: { project_id: projectId, body: `History line ${index}.`, reply_to: null },
    });
    expect(sent.ok()).toBe(true);
    lastSent = ((await sent.json()) as { id: number }).id;
  }
  // A job answers each message with a "No reply" status line, some time after it was sent. Wait for
  // the last one, so no line arrives below while this test counts and pages.
  await expect
    .poll(
      async () => {
        const newest = await page.request.get(`/v1/chat/history?project_id=${projectId}&limit=50`);
        const items = ((await newest.json()) as { items: { kind: string; reply_to: number | null }[] }).items;
        return items.some((item) => item.kind === "status" && item.reply_to === lastSent);
      },
      { timeout: 60_000, intervals: [250] },
    )
    .toBe(true);
  await page.reload();
  const line = (index: number): Locator =>
    page.getByTestId("message-person").getByText(`History line ${index}.`, { exact: true });
  await expect(line(120)).toBeVisible();
  await expect(line(1)).toHaveCount(0);
  const shown = page.locator("article.message[id^='message-']");
  const firstShown = await shown.count();
  expect(firstShown).toBeLessThanOrEqual(50);

  // The header above the chat fills in after the messages do, and moves the list down: wait for it.
  await expect(page.getByTestId("project-state")).toBeVisible();
  const earlier = page.getByRole("button", { name: "Show earlier messages" });
  await earlier.scrollIntoViewIfNeeded();
  const anchor = shown.first();
  const anchorId = await anchor.getAttribute("id");
  const top = (await anchor.boundingBox())?.y ?? 0;
  await earlier.click();
  await expect(shown.first()).not.toHaveAttribute("id", anchorId ?? "");
  expect(await shown.count()).toBeGreaterThan(firstShown);
  const after = (await page.locator(`#${anchorId}`).boundingBox())?.y ?? -1;
  expect(Math.abs(after - top)).toBeLessThanOrEqual(2);

  for (let pages = 0; pages < 10 && (await earlier.count()) > 0; pages += 1) {
    const oldest = (await shown.first().getAttribute("id")) ?? "";
    await earlier.click();
    await expect(shown.first()).not.toHaveAttribute("id", oldest);
  }
  await expect(earlier).toHaveCount(0);
  await expect(line(1)).toBeAttached();
  await expect(page.getByRole("log", { name: "Messages" })).toBeFocused();

  // New messages still arrive below while older pages are loaded.
  await sendMessage(page, "And one more line.");
  await expect(page.getByText("And one more line.", { exact: true })).toBeVisible();
});

test("a new project's recalled memory says what will fill it", async () => {
  await openPanel(page, "Memory");
  await panel().getByRole("tab", { name: "Recalled memory" }).click();
  await expect(panel()).toContainText("Nothing is remembered yet.");
  await expect(panel()).toContainText("Facts the agents pick up while they work will be listed here.");
  await page.getByRole("button", { name: "Close panel" }).click();
});
