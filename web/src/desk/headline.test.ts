/**
 * HUM-1, HUM-2, P4: every kind of decision item the server registers gets a plain headline from its
 * typed fields, its subject in the filer's own words (shown as plain text), and its size. The
 * kinds and field names are those of the Python registrations (domain/planning/items.py,
 * domain/decisions/{asks,flags,reviews,mistakes}.py, budget/service.py, work/reviews.py,
 * conversation/decisions.py).
 */
import { describe, expect, it } from "vitest";
import { headlineOf, isNote, money, settledWords, type Headline } from "./headline";

const LOCALE = "en-US";

type Case = [kind: string, fields: Record<string, unknown>, recommendation: string, expected: Headline];

const CASES: Case[] = [
  [
    "proposed scope",
    { requirement_id: 4, estimate_runs: 1, text: "Build a pricing page with three plans." },
    "Accept requirement 4 into scope.",
    { ask: "Add to scope?", subject: "Build a pricing page with three plans.", size: "1 run" },
  ],
  [
    "proposed commitment",
    { commitment_id: 2, projected: "12 Dec 2026 18:00 UTC" },
    "Accept the commitment at the platform's projection.",
    { ask: "Commit to finishing by 12 Dec 2026 18:00 UTC?", subject: null, size: null },
  ],
  [
    "verdict",
    { requirement_id: 7, success_test: "A reader finds the venue in plan.md." },
    "Look at the work and pass or reject the requirement.",
    { ask: "Give a verdict on requirement 7", subject: "A reader finds the venue in plan.md.", size: null },
  ],
  [
    "reserve draw",
    { draw_id: 1, tokens: 50000, reason: "The last requirement needs two more runs." },
    "Approve the draw so the nearly finished scope can be finished.",
    { ask: "Release 50,000 tokens from the reserve?", subject: "The last requirement needs two more runs.", size: null },
  ],
  [
    "approval: capacity",
    { request_id: 3, what: "budget", amount: 3000000 },
    "Raise the budget to 3,000,000.",
    { ask: "Raise the budget to 3,000,000?", subject: null, size: null },
  ],
  [
    "approval: spend",
    { amount: 15, currency: "USD" },
    "Approve $15 a month for Postmark so the welcome email reaches inboxes.",
    { ask: "Approve spending $15.00?", subject: "Approve $15 a month for Postmark so the welcome email reaches inboxes.", size: null },
  ],
  [
    "approval: legal",
    {},
    "Accept the provider's data processing terms.",
    { ask: "Approve a legal step?", subject: "Accept the provider's data processing terms.", size: null },
  ],
  [
    "approval: tool permission",
    { tool: "browser" },
    "Let the researcher open the provider's pricing pages.",
    { ask: "Allow the tool “browser”?", subject: "Let the researcher open the provider's pricing pages.", size: null },
  ],
  [
    "delivery sign-off",
    { deliverables: ["index.html", "pricing.html"] },
    "Open the deliverables, then sign the project off.",
    { ask: "Sign off the delivery", subject: null, size: "2 deliverables" },
  ],
  [
    "budget checkpoint",
    { spent: 1500000, budget: 2000000 },
    "Raise the budget, or let the project land on what is left.",
    { ask: "Raise the budget, or land the project?", subject: null, size: "1,500,000 of 2,000,000 tokens used" },
  ],
  [
    "audit sample",
    { audit_id: 1, task_id: 12, label: "words" },
    "Open the work this task closed on and pass or fail it.",
    { ask: "Spot-check task 12", subject: "words", size: null },
  ],
  [
    "reopen request",
    { request_id: 1, decision_id: 5, reason: "The provider changed its prices." },
    "Reopen the decision only if the new evidence changes the picture.",
    { ask: "Reopen decision 5?", subject: "The provider changed its prices.", size: null },
  ],
  [
    "question",
    { question: "Should the Team plan show a yearly price?", why: "It adds a row.", options: ["No", "Yes"], recommended: 2, default: "No", concerns: "other" },
    "Option 2: Yes",
    { ask: "Answer a question", subject: "Should the Team plan show a yearly price?", size: null },
  ],
  [
    "assist",
    { what: "captcha", step: "Solve the captcha on the sign-up page.", task_id: 9 },
    "Do this step for researcher, then mark it done.",
    { ask: "Do a step only you can do", subject: "Solve the captcha on the sign-up page.", size: "A captcha" },
  ],
  [
    "heads-up",
    { text: "The copy passed review." },
    "The copy passed review.",
    { ask: "Heads-up", subject: "The copy passed review.", size: null },
  ],
  [
    "flag",
    { flag: "stalled", key: "", type: "state", cause: "No task moved in two hours." },
    "No task moved in two hours.",
    { ask: "Flagged: stalled", subject: "No task moved in two hours.", size: null },
  ],
  [
    "mistake report",
    { because: "a task was redone three times", cost_tokens: 42000 },
    "The CEO owes a mistake report: a task was redone three times.",
    { ask: "A mistake report is owed", subject: "a task was redone three times", size: "42,000 tokens" },
  ],
  [
    "status review",
    { number: 3, green: false, narrative: "Pricing slipped a day.", numbers: {}, levers: [] },
    "Look at what is at risk and use a lever if one is needed.",
    { ask: "Status review 3: needs a look", subject: "Pricing slipped a day.", size: null },
  ],
];

describe("headlineOf: the ask in plain words for every registered kind (HUM-1, HUM-2)", () => {
  it.each(CASES)("%s", (kind, fields, recommendation, expected) => {
    expect(headlineOf({ kind, fields, recommendation, title: "The server's title" }, LOCALE)).toEqual(expected);
  });

  it("covers every kind the server registers", () => {
    expect(CASES.map(([kind]) => kind).sort()).toEqual(
      [
        "approval: capacity",
        "approval: legal",
        "approval: spend",
        "approval: tool permission",
        "assist",
        "audit sample",
        "budget checkpoint",
        "delivery sign-off",
        "flag",
        "heads-up",
        "mistake report",
        "proposed commitment",
        "proposed scope",
        "question",
        "reopen request",
        "reserve draw",
        "status review",
        "verdict",
      ].sort(),
    );
  });

  it("falls back to the server's title and the recommendation for a kind it does not know", () => {
    expect(headlineOf({ kind: "something new", fields: {}, recommendation: "Do the thing.", title: "Something new: 4" }, LOCALE)).toEqual({
      ask: "Something new: 4",
      subject: "Do the thing.",
      size: null,
    });
  });

  it("still says what is asked when typed fields are missing", () => {
    const bare = (kind: string): string => headlineOf({ kind, fields: {}, recommendation: "", title: "t" }, LOCALE).ask;
    expect(bare("approval: spend")).toBe("Approve spending?");
    expect(bare("verdict")).toBe("Give a verdict");
    expect(bare("proposed commitment")).toBe("Commit to a finish date?");
    expect(headlineOf({ kind: "proposed scope", fields: { estimate_runs: "x" }, recommendation: "", title: "t" }).size).toBeNull();
  });

  it("keeps agent text as given, markup and all, for the plain-text renderer (P4)", () => {
    const text = "<a href='https://evil.example'>click</a> [link](https://evil.example)";
    expect(headlineOf({ kind: "proposed scope", fields: { text }, recommendation: "", title: "t" }).subject).toBe(text);
  });
});

describe("money", () => {
  it("writes a known currency the local way, and an unknown one out", () => {
    expect(money(15, "USD", LOCALE)).toBe("$15.00");
    expect(money(1234.5, "eur", LOCALE)).toBe("€1,234.50");
    expect(money(15, "credits", LOCALE)).toBe("15.00 CREDITS");
    expect(money(15, null, LOCALE)).toBe("15.00");
  });
});

describe("settledWords: the line a settled card becomes", () => {
  it.each([
    [{ state: "decided", outcome: "approve" }, "You approved"],
    [{ state: "decided", outcome: "accept anyway" }, "You accepted anyway"],
    [{ state: "acknowledged", outcome: "acknowledge" }, "You acknowledged"],
    [{ state: "defaulted", outcome: "decline" }, "Declined by default"],
    [{ state: "defaulted", outcome: "the default stands" }, "Unanswered: the CEO's default stands"],
    [{ state: "defaulted", outcome: "something" }, "Settled by default: something"],
    [{ state: "withdrawn", outcome: null }, "Withdrawn"],
    [{ state: "void", outcome: null }, "No longer needed"],
    [{ state: "decided", outcome: "Accepted directly" }, "Settled: Accepted directly"],
  ])("%o → %s", (item, expected) => {
    expect(settledWords(item)).toBe(expected);
  });
});

describe("isNote", () => {
  it("treats what only tells as a note, and what asks as a card", () => {
    expect(["heads-up", "flag", "mistake report"].every(isNote)).toBe(true);
    expect(["question", "approval: spend", "status review", undefined].some(isNote)).toBe(false);
  });
});
