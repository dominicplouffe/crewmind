/** Reads a request to approve an AI client from the address, and builds the address a denial goes to. */

const APPROVAL_PATH = "#/oauth/approve";

export interface ApprovalRequest {
  clientId: string;
  redirectUri: string;
  /** The scopes the client asked for, without repeats. The person may drop some and add none. */
  scopes: string[];
  codeChallenge: string;
  codeChallengeMethod: string;
  resource: string;
  state: string;
}

export function isApprovalLink(hash: string): boolean {
  return hash === APPROVAL_PATH || hash.startsWith(`${APPROVAL_PATH}?`);
}

export function readApproval(hash: string): ApprovalRequest {
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  const text = (name: string): string => params.get(name) ?? "";
  return {
    clientId: text("client_id"),
    redirectUri: text("redirect_uri"),
    scopes: [...new Set(text("scope").split(/\s+/).filter(Boolean))],
    codeChallenge: text("code_challenge"),
    codeChallengeMethod: text("code_challenge_method"),
    resource: text("resource"),
    state: text("state"),
  };
}

/** Addresses that would run something in this page instead of leaving it. */
const NEVER_FOLLOWED = ["javascript:", "data:", "vbscript:", "blob:", "file:"];

/** Where the browser goes when the person says no, or null when the address cannot be followed. */
export function denialUrl(redirectUri: string, state: string): string | null {
  let url: URL;
  try {
    url = new URL(redirectUri);
  } catch {
    return null;
  }
  if (NEVER_FOLLOWED.includes(url.protocol)) return null;
  url.searchParams.set("error", "access_denied");
  if (state) url.searchParams.set("state", state);
  return url.toString();
}
