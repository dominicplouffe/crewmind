import { describe, expect, it } from "vitest";
import { denialUrl, isApprovalLink, readApproval } from "./oauth";

describe("approval link", () => {
  it("is recognised by its path after the hash", () => {
    expect(isApprovalLink("#/oauth/approve?client_id=a")).toBe(true);
    expect(isApprovalLink("#/oauth/approve")).toBe(true);
    expect(isApprovalLink("#/oauth/approved")).toBe(false);
    expect(isApprovalLink("")).toBe(false);
  });

  it("reads every part of the request, and each asked scope once", () => {
    const hash =
      "#/oauth/approve?client_id=c1&redirect_uri=http%3A%2F%2Flocalhost%3A7777%2Fcallback&scope=read+steer%20read" +
      "&code_challenge=abc&code_challenge_method=S256&resource=http%3A%2F%2Fhost%2Fmcp&state=xyz";
    expect(readApproval(hash)).toEqual({
      clientId: "c1",
      redirectUri: "http://localhost:7777/callback",
      scopes: ["read", "steer"],
      codeChallenge: "abc",
      codeChallengeMethod: "S256",
      resource: "http://host/mcp",
      state: "xyz",
    });
  });

  it("reads a link with nothing in it as empty values", () => {
    expect(readApproval("#/oauth/approve")).toMatchObject({ clientId: "", redirectUri: "", scopes: [], state: "" });
  });
});

describe("denialUrl", () => {
  it("adds the error and the state, keeping what the address already carried", () => {
    expect(denialUrl("http://localhost:7777/callback?x=1", "s 1")).toBe(
      "http://localhost:7777/callback?x=1&error=access_denied&state=s+1",
    );
    expect(denialUrl("myapp://done", "")).toBe("myapp://done?error=access_denied");
  });

  it.each(["", "not an address", "javascript:alert(1)", "data:text/html,hi"])("does not follow %j", (address) => {
    expect(denialUrl(address, "s")).toBeNull();
  });
});
