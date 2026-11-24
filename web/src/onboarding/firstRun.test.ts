/** FND-1, LLM-14: a new install's admin is sent to the setup screens once, and only then. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { markWelcomeSeen, opensWelcome, welcomeSeen } from "./firstRun";

const NEW_INSTALL = { isAdmin: true, founderReady: false, projects: 0, seen: false };

describe("opensWelcome", () => {
  it("sends an admin on an install that cannot draft a project yet", () => {
    expect(opensWelcome(NEW_INSTALL)).toBe(true);
  });

  it.each([
    ["a member, who cannot change install settings", { isAdmin: false }],
    ["an install whose Founder is set up", { founderReady: true }],
    ["an install that already has a project", { projects: 1 }],
    ["a browser that has shown the setup screens", { seen: true }],
  ])("does not send %s", (_, change) => {
    expect(opensWelcome({ ...NEW_INSTALL, ...change })).toBe(false);
  });
});

describe("welcomeSeen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("is remembered once the setup screens are shown", () => {
    expect(welcomeSeen()).toBe(false);
    markWelcomeSeen();
    expect(welcomeSeen()).toBe(true);
  });

  it("reads as seen when the browser keeps nothing, so nobody is sent in a loop", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(welcomeSeen()).toBe(true);
  });
});
