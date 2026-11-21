/**
 * End-to-end tests against a real crewmind server with the mock model.
 * Covers CHAT-1 to CHAT-4, CHAT-7, CHAT-9, CHAT-10, CHAT-14, CHAT-16, CHAT-18 to CHAT-20, ART-3, ART-4, NFR-18.
 */
import { expect, test, type Page } from "@playwright/test";
import {
  EMAIL,
  PASSWORD,
  PLAN_SCRIPT,
  STATE_FILE,
  createProject,
  expectAccessible,
  recordTyping,
  sendMessage,
  setCeoScript,
  setTheme,
  setupToken,
  typingSeen,
} from "./helpers";

test.describe.configure({ mode: "serial" });

let page: Page;
let projectUrl = "";

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext()).newPage();
});

test.afterAll(async () => {
  await page.context().close();
});

const agentMessages = (): ReturnType<Page["locator"]> => page.getByTestId("message-agent");

test("signed-out visitors are sent to sign in, and the page is accessible (NFR-18)", async () => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in to crewmind" })).toBeVisible();
  await expectAccessible(page, "sign-in page");
});

test("a setup link sets the password, shows the server's refusal, then signs in", async () => {
  await page.goto(`/accept/${setupToken()}`);
  await page.getByLabel("New password", { exact: true }).fill("short");
  await page.getByLabel("New password, again").fill("short");
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByRole("alert")).toContainText("at least 12 characters");
  await expect(page.getByRole("alert")).toContainText("Choose a longer password.");

  await page.getByLabel("New password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("New password, again").fill(PASSWORD);
  await page.getByRole("button", { name: "Set password" }).click();
  await expect(page.getByText("Your password is set.")).toBeVisible();

  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill("wrong password here");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();

  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await page.context().storageState({ path: STATE_FILE });
});

test("the project list says what to do when empty and is accessible", async () => {
  await expect(page.getByText("You have no projects yet.")).toBeVisible();
  await expectAccessible(page, "project list");
});

test("create and start a project (CHAT-1, CHAT-18)", async () => {
  await createProject(page, "Plan project");
  projectUrl = page.url();
  await expect(page.getByTestId("project-state")).toHaveText("draft");
  await expect(page.getByText("This project has not started.")).toBeVisible();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByTestId("project-state")).toHaveText("running");
  await expect(page.getByRole("button", { name: "Hold" })).toBeVisible();
  await expect(page.getByText(/of [\d,]+ tokens used/)).toBeVisible();
});

test("a sent message shows as delivered and the reply streams in (CHAT-3, CHAT-10, CHAT-11)", async () => {
  await recordTyping(page);
  await sendMessage(page, "Please make a plan");
  await expect(page.getByTestId("delivered").first()).toBeVisible({ timeout: 3000 });
  const reply = agentMessages().first();
  await expect(reply).toContainText("Here is the plan", { timeout: 30_000 });
  await expect(page.getByTestId("typing")).toHaveCount(0);
  // The mock streams the whole reply within a few hundred milliseconds, so check what the bubble showed.
  const seen = await typingSeen(page);
  expect(seen.length).toBeGreaterThan(0);
  expect(seen.join(" ")).toContain("Here");
  await expect(reply.locator("strong")).toHaveText("plan");
  await expect(reply.locator("pre code.hljs")).toContainText("print(1)");
  await expect(reply.getByRole("button", { name: /In reply to Admin/ })).toContainText("Please make a plan");
});

test("/hold changes the header and /resume changes it back (CHAT-5, CHAT-18)", async () => {
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill("/ho");
  await expect(page.getByRole("option", { name: /\/hold/ })).toBeVisible();
  await box.press("Enter");
  await expect(box).toHaveValue("/hold ");
  await box.press("Enter");
  await expect(page.getByTestId("project-state")).toHaveText("held");
  await expect(page.getByText(/Lifted by:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await expect(page.getByTestId("notice-result").last()).toContainText("Done: /hold");

  await sendMessage(page, "/nonsense");
  await expect(page.getByRole("alert").filter({ hasText: "There is no command /nonsense" })).toContainText(
    "Type /help to see what each one does.",
  );
  await page.getByRole("button", { name: "Dismiss" }).last().click();

  await sendMessage(page, "/resume");
  await expect(page.getByTestId("project-state")).toHaveText("running");
});

test("@ completes agents, and Up arrow recalls the last message (CHAT-4)", async () => {
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill("@C");
  await expect(page.getByRole("option", { name: /@CEO/ })).toBeVisible();
  await box.press("Tab");
  await expect(box).toHaveValue("@CEO ");
  await box.fill("");
  await box.press("ArrowUp");
  await expect(box).toHaveValue("Please make a plan");
  await box.fill("");
});

test("upload files and preview them: markdown, CSV, and HTML in a locked frame (CHAT-9, CHAT-16)", async () => {
  await page.getByTestId("file-picker").setInputFiles([
    { name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("# Field notes\n\nSome *text*.") },
    { name: "table.csv", mimeType: "text/csv", buffer: Buffer.from('name,quote\nAda,"Hello, ""world"""\n') },
    {
      name: "page.html",
      mimeType: "text/html",
      buffer: Buffer.from('<h1>Report</h1><script>parent.document.title="pwned"</script><img src="https://example.com/x.png">'),
    },
  ]);
  await page.getByRole("button", { name: "Preview notes.md" }).click();
  const panel = page.getByTestId("panel");
  await expect(panel.getByRole("heading", { name: "Field notes" })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Download version 1" })).toBeVisible();

  await panel.getByRole("button", { name: "Back to all files" }).click();
  await panel.getByRole("button", { name: "table.csv", exact: true }).click();
  await expect(panel.getByTestId("csv-table").getByRole("cell", { name: 'Hello, "world"' })).toBeVisible();

  await panel.getByRole("button", { name: "Back to all files" }).click();
  await panel.getByRole("button", { name: "page.html", exact: true }).click();
  const frame = panel.getByTestId("html-frame");
  await expect(frame).toHaveAttribute("sandbox", "");
  await expect(frame).toHaveAttribute("srcdoc", /Content-Security-Policy.*default-src 'none'/);
  await expect(page.frameLocator('[data-testid="html-frame"]').getByRole("heading", { name: "Report" })).toBeVisible();
  expect(await page.title()).not.toBe("pwned");
});

test("lock a file, mark an upload as reference, and compare two versions (ART-3, ART-4, ART-5)", async () => {
  await page.getByTestId("file-picker").setInputFiles([
    { name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("# Field notes\n\nSome *better* text.\nA new line.") },
  ]);
  const panel = page.getByTestId("panel");
  await panel.getByRole("button", { name: "Back to all files" }).click();
  const row = panel.getByTestId("file-row").filter({ hasText: "notes.md" });
  await expect(row).toContainText("2 versions");
  await row.getByRole("button", { name: /Mark as reference/ }).click();
  await expect(row).toContainText("marked as reference");
  await row.getByRole("button", { name: /^Lock/ }).click();
  await expect(row).toContainText("locked");
  await row.getByRole("button", { name: /^Unlock/ }).click();
  await expect(row).not.toContainText("locked");

  await row.getByRole("button", { name: "notes.md", exact: true }).click();
  await panel.getByRole("button", { name: "Compare versions" }).click();
  const diff = panel.getByTestId("diff-table");
  await expect(diff).toContainText("Some *text*.");
  await expect(diff).toContainText("Some *better* text.");
  await expect(diff.locator("tr.diff-added")).toContainText("A new line.");
  await page.getByRole("button", { name: "Close panel" }).click();
});

test("a file over 1 MB goes up in chunks (CHAT-9)", async () => {
  const big = Buffer.alloc(1_600_000, "a");
  await page.getByTestId("file-picker").setInputFiles([{ name: "big.txt", mimeType: "text/plain", buffer: big }]);
  await expect(page.getByRole("button", { name: "Preview big.txt" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Files", exact: true }).click();
  await expect(page.getByTestId("file-row").filter({ hasText: "big.txt" })).toContainText("1.5 MB");
  await page.getByRole("button", { name: "Close panel" }).click();
});

test("accept an action card with one tap (CHAT-7)", async () => {
  setCeoScript([
    {
      tools: [
        {
          name: "agent_propose_action",
          arguments: { what: "Hire a research team of two.", estimated_tokens: 400000, reversible: true },
        },
      ],
    },
    { text: "" },
  ]);
  await sendMessage(page, "What do you suggest?");
  const card = page.getByTestId("action-card").last();
  await expect(card).toContainText("Hire a research team of two.", { timeout: 30_000 });
  await expect(card).toContainText("About 400,000 tokens. It can be undone.");
  await expect(card.getByRole("button", { name: "Not now" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Edit" })).toBeVisible();
  await card.getByRole("button", { name: "Do it" }).click();
  await expect(card).toContainText("You said: do it.");
  setCeoScript(PLAN_SCRIPT);
});

test("the command palette opens panels; budget, models, settings, runs, activity and search work", async () => {
  await page.keyboard.press("Control+k");
  await page.getByRole("dialog", { name: "Command palette" }).getByRole("textbox").fill("budget");
  await page.keyboard.press("Enter");
  const panel = page.getByTestId("panel");
  await expect(panel.getByRole("heading", { name: "Budget" })).toBeFocused();
  await expect(panel).toContainText("Cache reads do not count against the budget.");
  await expect(panel).toContainText("Remaining");

  await page.getByRole("button", { name: "Models", exact: true }).click();
  await expect(panel).toContainText("Runs on mock-frontier (mock)");

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const setting = panel.getByTestId("setting-run.concurrency");
  await expect(setting).toContainText("Allowed: 1–16");
  await setting.getByRole("button", { name: /Change/ }).click();
  await setting.getByLabel("New value for run.concurrency").fill("5");
  await setting.getByLabel("Why are you changing it?").fill("short");
  await setting.getByRole("button", { name: "Save" }).click();
  await expect(setting.getByRole("alert")).toContainText("needs a reason of at least 10 characters");
  await setting.getByLabel("Why are you changing it?").fill("Trying more parallel work.");
  await setting.getByRole("button", { name: "Save" }).click();
  await expect(setting.locator(".setting-value")).toHaveText("5");

  await page.getByRole("button", { name: "Runs", exact: true }).click();
  await panel.getByRole("button", { name: /CEO · chat · finished/ }).first().click();
  await expect(panel.getByTestId("run-trace")).toContainText("Steps");
  await expect(panel.getByTestId("run-trace")).toContainText("model call");

  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(panel.getByRole("list", { name: "Activity, newest first" })).toContainText("A chat run is now finished.");

  await page.getByRole("button", { name: "Search", exact: true }).click();
  await panel.getByRole("searchbox").fill("plan");
  await panel.getByRole("searchbox").press("Enter");
  await panel.getByRole("button", { name: /go to message/ }).first().click();
  await expect(page.locator("article.message:focus")).toContainText("plan");
  await page.getByRole("button", { name: "Close panel" }).click();
});

test("replies open as a thread, and a message links to its run (CHAT-11, CHAT-14)", async () => {
  await agentMessages().first().getByRole("button", { name: "Open thread" }).click();
  const panel = page.getByTestId("panel");
  await expect(panel.getByTestId("thread")).toContainText("Please make a plan");
  await expect(panel.getByTestId("thread")).toContainText("Here is the plan");
  await agentMessages().first().getByRole("button", { name: /How this was made/ }).click();
  await expect(panel.getByTestId("run-trace")).toContainText("Why it ran");
  await page.getByRole("button", { name: "Close panel" }).click();
});

test("the theme switch works and the project page is accessible in both themes (NFR-18)", async () => {
  await setTheme(page, "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(15, 20, 28)");
  await setTheme(page, "light");
  await expectAccessible(page, "project page");
  await page.getByRole("button", { name: "Files", exact: true }).click();
  await expect(page.getByTestId("file-row").first()).toBeVisible();
  await expectAccessible(page, "project page with the files panel");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByTestId("setting-quality")).toBeVisible();
  await expectAccessible(page, "project page with the settings panel");
  await page.getByRole("button", { name: "Close panel" }).click();
});

test("the reply bubble grows as words arrive, and Esc asks the server to stop the run (CHAT-3, CHAT-4)", async () => {
  setCeoScript([{ text: Array.from({ length: 2500 }, (_, index) => `w${index}`).join(" ") }]);
  await sendMessage(page, "Write something long");
  const bubble = page.getByTestId("typing");
  await expect(bubble).toContainText("w5 ", { timeout: 30_000 });
  await expect(bubble).toContainText("w300 ");
  await expect(bubble.getByRole("button", { name: "Stop" })).toBeVisible();
  const asked = page.waitForRequest((request) => request.url().endsWith("/v1/runs/interrupt"));
  await page.getByRole("textbox", { name: "Message" }).press("Escape");
  const request = await asked;
  expect(request.postDataJSON()).toMatchObject({ run_id: expect.stringMatching(/^[0-9a-f]{32}$/) });
  const response = await request.response();
  if (response?.ok()) {
    await expect(bubble).toHaveCount(0);
  } else {
    // The mock run has already finished when its words stream, so the server refuses; its words are shown.
    const refusal = (await response?.json()) as { message: string };
    await expect(page.getByTestId("notice-error").last()).toContainText(refusal.message);
    await page.getByTestId("notice-error").last().getByRole("button", { name: "Dismiss" }).click();
  }
  setCeoScript(PLAN_SCRIPT);
  await expect(bubble).toHaveCount(0, { timeout: 40_000 });
  await expect(agentMessages().last()).toContainText("w2499");
  await expect(agentMessages().last().getByRole("button", { name: "Show more" })).toBeVisible();
});

test("polling keeps the chat working when the live stream is blocked", async () => {
  await page.route("**/stream/v1/**", (route) => route.abort());
  await page.reload();
  await expect(page.getByText("Live updates stopped.")).toBeVisible();
  const before = await agentMessages().count();
  await sendMessage(page, "Are you still there?");
  await expect(agentMessages()).toHaveCount(before + 1, { timeout: 40_000 });
  await page.unroute("**/stream/v1/**");
});

test.describe("on a 390 px wide phone (CHAT-20)", () => {
  test.use({ viewport: { width: 390, height: 844 }, storageState: STATE_FILE });

  test("the chat fits, panels open as full-screen sheets, and it is accessible", async ({ page: phone }) => {
    await phone.goto(projectUrl);
    await expect(phone.getByTestId("project-state")).toHaveText("running");
    await expect(phone.getByTestId("message-agent").first()).toBeVisible();
    const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await expectAccessible(phone, "project page on a phone");

    await phone.getByRole("button", { name: "Files", exact: true }).click();
    const box = await phone.getByTestId("panel").boundingBox();
    expect(box?.width).toBe(390);
    expect(box?.height).toBe(844);
    await expectAccessible(phone, "files sheet on a phone");
    await phone.getByRole("button", { name: "Close panel" }).click();
    await expect(phone.getByRole("textbox", { name: "Message" })).toBeFocused();

    await sendMessage(phone, "Hello from a phone");
    await expect(phone.getByText("Hello from a phone")).toBeVisible();
    await expect(phone.getByTestId("delivered").last()).toBeVisible();
  });
});

test.describe("installable app (CHAT-20)", () => {
  test.use({ serviceWorkers: "allow", storageState: STATE_FILE });

  test("the manifest and service worker load, and API answers are never cached", async ({ page: app }) => {
    await app.goto("/");
    const manifest = await app.request.get("/manifest.webmanifest");
    expect(manifest.ok()).toBe(true);
    expect((await manifest.json()).display).toBe("standalone");
    for (const icon of ["/icon-192.png", "/icon-512.png", "/icon.svg"]) {
      expect((await app.request.get(icon)).ok()).toBe(true);
    }
    await app.evaluate(async () => {
      await navigator.serviceWorker.ready;
    });
    await app.reload();
    await expect(app.getByRole("heading", { name: "Projects" })).toBeVisible();
    const cached = await app.evaluate(async () => {
      const urls: string[] = [];
      for (const name of await caches.keys()) {
        for (const request of await (await caches.open(name)).keys()) urls.push(new URL(request.url).pathname);
      }
      return urls;
    });
    expect(cached).toContain("/");
    expect(cached.filter((path) => /^\/(v1|files|stream)\//.test(path))).toEqual([]);
  });
});
