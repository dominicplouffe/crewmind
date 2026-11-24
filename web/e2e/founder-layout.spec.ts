/**
 * End-to-end test of the drafting page's layout against a real nightsquad server: at common window
 * widths, with the app's sidebar beside it, the conversation keeps a readable width and the
 * Founder's name stays on one line (FND-1, NFR-18).
 * It runs after app.spec.ts (one worker, files in name order) and reuses its signed-in session.
 */
import { expect, test } from "@playwright/test";
import { STATE_FILE, setFounderScript } from "./helpers";

const SHOTS = process.env.NIGHTSQUAD_E2E_SHOTS;
const BRIEF = "Every day, research new AI tools and write a long blog post about them, with charts and a hero image.";

test("the conversation keeps a readable width beside the decisions and the draft (FND-1, NFR-18)", async ({ browser }) => {
  setFounderScript([{ text: "I'm setting up an **operate** project: a daily post about new AI tools." }], []);
  const page = await (await browser.newContext({ storageState: STATE_FILE, viewport: { width: 1920, height: 1000 } })).newPage();
  await page.goto("/draft");
  await page.getByLabel("What do you want done?").fill(BRIEF);
  await page.getByRole("button", { name: "Start drafting" }).click();
  const log = page.getByRole("log");
  await expect(log.getByText("a daily post about new AI tools")).toBeVisible();

  for (const width of [390, 1100, 1366, 1440, 1600, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    const main = page.locator(".draft-main");
    const box = await main.boundingBox();
    expect(box?.width ?? 0, `conversation width at ${width}px`).toBeGreaterThanOrEqual(Math.min(480, width - 60));
    const author = log.getByTestId("line-founder").first().locator(".author");
    const line = await author.evaluate((element) => {
      const style = getComputedStyle(element);
      return element.getBoundingClientRect().height <= parseFloat(style.lineHeight) * 1.5;
    });
    expect(line, `the Founder's name fits one line at ${width}px`).toBe(true);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/draft-${width}.png` });
  }
  await page.context().close();
});

test("a message to the Founder shows it working at once, until its answer arrives (FND-1, P17)", async ({ browser }) => {
  setFounderScript(
    [
      { text: "I'm setting up a daily post about new AI tools." },
      { text: "I will use an image model for the hero images.", delay_ms: 4000 },
    ],
    [],
  );
  const page = await (await browser.newContext({ storageState: STATE_FILE, viewport: { width: 1440, height: 900 } })).newPage();
  await page.goto("/draft");
  await page.getByLabel("What do you want done?").fill(BRIEF);
  await page.getByRole("button", { name: "Start drafting" }).click();
  const log = page.getByRole("log");
  await expect(log.getByText("a daily post about new AI tools")).toBeVisible();

  const box = page.getByRole("textbox", { name: "Message to the Founder" });
  await box.fill("What will you use to create the hero images?");
  await box.press("Enter");
  // At once: the Founder is shown working in the conversation, and the box waits for it.
  await expect(page.getByTestId("founder-thinking")).toBeVisible({ timeout: 3000 });
  await expect(page.getByTestId("founder-thinking")).toBeInViewport();
  await expect(page.getByTestId("draft-composer")).toHaveAttribute("data-mode", "working");
  await expect(page.getByTestId("now")).toHaveAttribute("data-now", /writing-first|updating/);
  // Then its answer replaces the bubble.
  await expect(log.getByText("I will use an image model for the hero images.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("founder-thinking")).toHaveCount(0);
  await page.context().close();
});
