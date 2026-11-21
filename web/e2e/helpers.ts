/** Shared pieces for the end-to-end tests. */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

const runDir = join(dirname(fileURLToPath(import.meta.url)), ".run");

export const EMAIL = "dom@example.com";
export const PASSWORD = "correct horse battery 9";
export const STATE_FILE = join(runDir, "signed-in.json");
export const PLAN_SCRIPT = [{ text: "Here is the **plan**:\n\n1. Research\n2. Draft\n\n```python\nprint(1)\n```" }];

export function setupToken(): string {
  const setup = JSON.parse(readFileSync(join(runDir, "setup.json"), "utf8")) as { setup_link: string };
  return new URL(setup.setup_link).pathname.split("/").pop() ?? "";
}

/** Replaces what the mock CEO does on its next chat run. */
export function setCeoScript(turns: unknown[]): void {
  writeFileSync(join(runDir, "scripts", "CEO.chat.json"), JSON.stringify(turns));
}

export async function setTheme(page: Page, theme: "light" | "dark"): Promise<void> {
  const current = await page.locator("html").getAttribute("data-theme");
  if (current !== theme) {
    const button = page.getByRole("button", { name: "Dark theme" }).first();
    if (await button.isVisible()) {
      await button.click();
    } else {
      // A full-screen sheet covers the button on a phone: use the command palette instead.
      await page.keyboard.press("Control+k");
      await page.getByRole("dialog", { name: "Command palette" }).getByRole("textbox").fill("light and dark");
      await page.keyboard.press("Enter");
    }
  }
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

/** Fails on any WCAG 2 A or AA violation, in the light theme and then the dark theme. */
export async function expectAccessible(page: Page, label: string): Promise<void> {
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    const summary = results.violations.map(
      (violation) => `${violation.id}: ${violation.help} (${violation.nodes.map((node) => node.target.join(" ")).join(", ")})`,
    );
    expect(summary, `${label}, ${theme} theme`).toEqual([]);
  }
  await setTheme(page, "light");
}

export async function createProject(page: Page, name: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Type").selectOption("deliver");
  await page.getByLabel("Goal").fill("Write a short plan.");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
}

export async function sendMessage(page: Page, text: string): Promise<void> {
  const box = page.getByRole("textbox", { name: "Message" });
  await box.fill(text);
  await box.press("Enter");
}

/** Records every text the "typing" bubble shows, so a short stream can still be checked afterwards. */
export async function recordTyping(page: Page): Promise<void> {
  await page.evaluate(() => {
    const seen: string[] = [];
    (window as unknown as { typingSeen: string[] }).typingSeen = seen;
    new MutationObserver(() => {
      const bubble = document.querySelector('[data-testid="typing"] .body');
      const text = bubble?.textContent ?? "";
      if (bubble && seen[seen.length - 1] !== text) seen.push(text);
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  });
}

export function typingSeen(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { typingSeen: string[] }).typingSeen);
}
