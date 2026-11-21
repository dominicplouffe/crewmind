/**
 * Phone and installed-app tests (CHAT-20, NFR-18). They run after app.spec.ts (one worker, files in
 * name order) and reuse the signed-in session and the project it created.
 */
import { expect, test } from "@playwright/test";
import { STATE_FILE, expectAccessible, projectUrl, sendMessage } from "./helpers";

test.describe("on a 390 px wide phone (CHAT-20)", () => {
  test.use({ viewport: { width: 390, height: 844 }, storageState: STATE_FILE });

  test("the chat fits, panels open as full-screen sheets, and it is accessible", async ({ page: phone }) => {
    await phone.goto(projectUrl());
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
