/**
 * The first time an admin opens Home on an install that cannot draft a project yet, Home sends
 * them to the setup screens at `/welcome` (FND-1, LLM-14): a new install needs a model key and
 * the Founder before anything else works. It happens once per browser; after that, the banner on
 * Home leads back. A browser that keeps nothing is never sent, so nobody is sent in a loop.
 */

const WELCOME_SEEN = "nightsquad.welcome-seen";

export interface FirstRunState {
  isAdmin: boolean;
  founderReady: boolean;
  projects: number;
  seen: boolean;
}

/** Whether Home should open the setup screens instead of showing itself. */
export function opensWelcome({ isAdmin, founderReady, projects, seen }: FirstRunState): boolean {
  return isAdmin && !founderReady && projects === 0 && !seen;
}

/** Whether this browser has shown the setup screens. True when the browser keeps nothing. */
export function welcomeSeen(): boolean {
  try {
    return window.localStorage.getItem(WELCOME_SEEN) === "1";
  } catch {
    return true;
  }
}

export function markWelcomeSeen(): void {
  try {
    window.localStorage.setItem(WELCOME_SEEN, "1");
  } catch {
    // Not remembered; welcomeSeen() then reads as true, so Home never sends anyone here.
  }
}
