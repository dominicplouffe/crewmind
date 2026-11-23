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

/** What a mock agent does when it has nothing scripted: one turn with no tools, which ends the run. */
export const IDLE_SCRIPT = [{ text: "Nothing to do." }];

/**
 * Replaces what a mock agent does on its next work run (`<seat>.work.json`). Scripts are read again on
 * every run, and a run that creates tasks wakes the CEO again: set the script back to IDLE_SCRIPT as
 * soon as the tasks exist, or the next run creates them a second time.
 */
export function setWorkScript(seat: "CEO" | "Reviewer", turns: unknown[]): void {
  writeFileSync(join(runDir, "scripts", `${seat}.work.json`), JSON.stringify(turns));
}

/**
 * Scripts a mock agent's work runs one by one: its next run plays `runs[0]`, the one after `runs[1]`,
 * and every later run plays `then`. Nothing is repeated, so the script need not be set back.
 */
export function setWorkRuns(seat: "CEO" | "Reviewer", runs: unknown[][], then: unknown[] = IDLE_SCRIPT): void {
  writeFileSync(join(runDir, "scripts", `${seat}.work.json`), JSON.stringify({ runs, then }));
}

/**
 * Scripts the mock Founder. `turns` is one list played through a whole drafting conversation, a turn
 * per model call; `grades` is what its grader answers for every goal (the ten element grades).
 */
export function setFounderScript(turns: unknown[], grades: unknown[]): void {
  writeFileSync(join(runDir, "scripts", "founder.draft.json"), JSON.stringify(turns));
  writeFileSync(join(runDir, "scripts", "founder.grade.json"), JSON.stringify([{ text: JSON.stringify(grades) }]));
}

/** One scripted turn that calls these agent tools in order. */
export function toolTurn(...tools: [name: string, args: Record<string, unknown>][]): unknown {
  return { text: "Working.", tools: tools.map(([name, args]) => ({ name, arguments: args })) };
}

/**
 * Puts the page in a theme for the accessibility scans. On signed-in pages it uses the user menu,
 * as a person would; on pages without one (sign-in) it sets the theme the app would apply.
 */
export async function setTheme(page: Page, theme: "light" | "dark"): Promise<void> {
  const current = await page.locator("html").getAttribute("data-theme");
  if (current !== theme) {
    const menu = page.getByTestId("user-menu").filter({ visible: true }).first();
    const covered = (await page.locator("dialog[open]").count()) > 0 || (await page.getByTestId("panel").count()) > 0;
    if ((await menu.count()) > 0 && (await menu.isVisible()) && !covered) {
      await menu.click();
      await page.getByRole("menuitemradio", { name: theme === "dark" ? "Dark" : "Light" }).click();
    } else {
      await page.evaluate((value) => {
        document.documentElement.dataset.theme = value;
      }, theme);
    }
  }
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

/** Opens a project tool by name ("Files", "Settings", "Runs"…) through the command palette. */
export async function openPanel(page: Page, name: string): Promise<void> {
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await palette.getByRole("combobox").fill(`open ${name}`);
  await palette.getByRole("option", { name: new RegExp(`^Open ${name}\\b`) }).first().click();
  await expect(page.getByTestId("panel").getByRole("heading", { name, exact: true })).toBeVisible();
}

/** Fails on any WCAG 2 A or AA violation in the page as it is now. */
export async function expectNoViolations(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map(
    (violation) => `${violation.id}: ${violation.help} (${violation.nodes.map((node) => node.target.join(" ")).join(", ")})`,
  );
  expect(summary, label).toEqual([]);
}

/** Fails on any WCAG 2 A or AA violation, in the light theme and then the dark theme. */
export async function expectAccessible(page: Page, label: string): Promise<void> {
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await expectNoViolations(page, `${label}, ${theme} theme`);
  }
  await setTheme(page, "light");
}

export async function createProject(page: Page, name: string): Promise<void> {
  await page.goto("/projects");
  await page.getByRole("button", { name: "Fill in a form instead" }).click();
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

const projectUrlFile = join(runDir, "project-url.txt");

export function saveProjectUrl(url: string): void {
  writeFileSync(projectUrlFile, url);
}

export function projectUrl(): string {
  return readFileSync(projectUrlFile, "utf8");
}

/**
 * The name an agent goes by in the project the page shows (EXE-18): the CEO and the reviewer draw a
 * first name, so tests ask the roster rather than assume one.
 */
export async function agentName(page: Page, seat = "CEO"): Promise<string> {
  const projectId = new URL(page.url()).pathname.split("/")[2] ?? "";
  return page.evaluate(
    async ([id, wanted]) => {
      const response = await fetch(`/v1/roster/show?project_id=${encodeURIComponent(id ?? "")}`, { credentials: "same-origin" });
      const roster = (await response.json()) as { seats: { name: string; display_name: string }[] };
      return roster.seats.find((item) => item.name === wanted)?.display_name ?? wanted ?? "";
    },
    [projectId, seat],
  );
}
