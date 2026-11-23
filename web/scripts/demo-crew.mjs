// Seeds a busy demo project on a mock-model server, for design reviews and screenshots.
//   e2e/start-backend.sh 8460 /tmp/crewmind-demo
//   node scripts/demo-crew.mjs http://127.0.0.1:8460 /tmp/crewmind-demo
// It signs the admin in (setting the password from the setup link on first use), names them,
// creates "Fieldnotes launch site", hires a crew, and scripts the mock agents through a day of
// work: requirements proposed and accepted, tasks claimed, written, reviewed and blocked, files
// delivered, tokens spent, and a spend approval and a question waiting on the chairman.
// It uses only the public API and the mock model's scripts; it changes no rule.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { request } from "playwright";

const [base = "http://127.0.0.1:8460", runDir = "/tmp/crewmind-demo"] = process.argv.slice(2);
const EMAIL = "dom@example.com";
const PASSWORD = "correct horse battery 9";
const scripts = join(runDir, "scripts");
const log = (...args) => console.log("·", ...args);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const tool = (...tools) => ({ text: "Working on it.", usage: { input: 90_000, output: 9_000 }, tools: tools.map(([name, args]) => ({ name: `agent_${name}`, arguments: args })) });
const say = (text, input = 40_000) => ({ text, usage: { input, output: 3_000 } });
const IDLE = [{ text: "Nothing to do right now.", usage: { input: 2_000, output: 50 } }];

/**
 * Scripts a seat's next runs of one kind. The mock counts runs from the first one of that seat and
 * kind, so the runs already made are padded with idle turns.
 */
let projectRef = "";
async function script(seat, kind, runs, then = IDLE) {
  const made = projectRef
    ? ((await get(`/v1/runs/list?project_id=${projectRef}&limit=200`))?.items ?? []).filter((run) => run.seat === seat && run.kind === kind).length
    : 0;
  writeFileSync(join(scripts, `${seat}.${kind}.json`), JSON.stringify({ runs: [...Array(made).fill(IDLE), ...runs], then }));
}

const api = await request.newContext({ baseURL: base });
async function call(method, path, data) {
  const response = method === "GET" ? await api.get(path) : await api.post(path, { data });
  const text = await response.text();
  if (!response.ok()) {
    log(`! ${path} ${response.status()} ${text.slice(0, 200)}`);
    return null;
  }
  return text ? JSON.parse(text) : null;
}
const get = (path) => call("GET", path);
const post = (path, data) => call("POST", path, data);

/** Waits until no run of the project is queued or running. */
async function settle(projectId, label, limit = 60_000) {
  const until = Date.now() + limit;
  await sleep(800);
  while (Date.now() < until) {
    const runs = (await get(`/v1/runs/list?project_id=${projectId}&limit=200`))?.items ?? [];
    if (runs.every((run) => run.ended_at !== null)) {
      log(`${label}: ${runs.length} runs so far`);
      return;
    }
    await sleep(500);
  }
  log(`${label}: still running after ${limit / 1000}s, going on`);
}

// ---- Sign in ------------------------------------------------------------------------------
const setup = JSON.parse(readFileSync(join(runDir, "setup.json"), "utf8"));
await post("/v1/auth/use_link", { link: setup.setup_link, password: PASSWORD });
if (!(await post("/v1/auth/login", { email: EMAIL, password: PASSWORD }))) process.exit(1);
await post("/v1/auth/set_name", { name: "Alex Rivera" });
log("signed in");

// ---- The project and its crew ---------------------------------------------------------------
const project = await post("/v1/projects/create", {
  name: "Fieldnotes launch site",
  type: "deliver",
  goal: "Ship a one-page marketing site for Fieldnotes, a note-taking app for field researchers: copy that explains it in one screen, a pricing table, a working sign-up form, and a launch checklist.",
});
const P = project.project_id;
projectRef = P;
const ref = { project_id: P };
await post("/v1/settings/change_project", {
  ...ref,
  changes: { "budget.tokens": 2_000_000, "authority.accept_scope": "chairman", "authority.verdict": "chairman" },
  reason: "A small launch: the chairman reviews scope and verdicts.",
});
await post("/v1/roster/hire_team", { ...ref, team: "web", role: "Software Engineer", names: ["Theo"] });
await post("/v1/roster/hire_team", { ...ref, team: "backend", role: "Software Engineer", names: ["Priya"] });
await post("/v1/roster/hire_team", { ...ref, team: "words", role: "Marketing", names: ["Maya"] });
log("crew hired");

await script("CEO", "work", [[say("Reading the goal and the crew. Nothing to plan until the chairman says go.", 30_000)]]);
await post("/v1/projects/start", ref);
await settle(P, "started");

// ---- The CEO plans: four requirements ------------------------------------------------------
const requirement = (text, success_test, estimate_runs) => ["propose_requirement", { text, test_kind: "observable", success_test, estimate_runs }];
await script("CEO", "work", [
  [
    tool(
      requirement("The landing page explains Fieldnotes in one screen.", "A reader can say what Fieldnotes does after ten seconds on the page.", 3),
      requirement("The pricing table lists Free, Pro and Team with monthly prices.", "A reader finds all three plans and their prices without scrolling past the table.", 2),
      requirement("The sign-up form creates an account and sends a welcome email.", "Signing up with a new address shows a welcome screen and the email arrives.", 4),
      requirement("A launch checklist covers analytics, SEO and the status page.", "Every item on the checklist names an owner and a done state.", 1),
    ),
    say("I have proposed four requirements. The first three are the launch; the checklist can wait if the budget is tight."),
  ],
]);
await post("/v1/chat/command", { ...ref, text: "/do Turn the goal into requirements we can check." });
await settle(P, "requirements proposed");
const plan = await get(`/v1/plan/show?project_id=${P}`);
const ids = plan.requirements.map((item) => item.id);
for (const id of ids.slice(0, 3)) await post("/v1/requirements/accept", { ...ref, requirement_id: id, anyway: true });
log(`accepted ${ids.slice(0, 3).join(", ")}; left ${ids[3]} proposed`);
// Accepting scope wakes the CEO. Let that run end first: a directive sent while it is live joins it
// (one run per agent at a time), and the scripted turn below would be played by the wrong run.
await settle(P, "scope accepted");

// ---- The members are scripted before their tasks exist: a new task wakes them at once -------
const LANDING = `# Fieldnotes\n\n## Your field notebook, finally searchable.\n\nFieldnotes keeps every observation, photo and voice memo from the field in one place, and finds any of them in a second.\n\n- **Works offline.** Take notes on a ridge with no signal; they sync when you are back.\n- **Tags itself.** Place, time and weather are added to every note.\n- **Shares cleanly.** Export a season of notes as a tidy report for your team.\n\n[Start free](#signup)\n`;
const PRICING = `<!doctype html><html><head><meta charset="utf-8"><title>Pricing</title><style>body{font-family:system-ui;margin:24px;color:#1c2024}h1{font-size:22px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:10px;text-align:left}th{background:#f4f4f8}</style></head><body><h1>Pricing</h1><table><tr><th>Plan</th><th>Price</th><th>For</th></tr><tr><td>Free</td><td>$0</td><td>One researcher, 500 notes</td></tr><tr><td>Pro</td><td>$9 / month</td><td>Unlimited notes, offline maps</td></tr><tr><td>Team</td><td>$29 / month</td><td>Shared projects and exports</td></tr></table></body></html>`;
const PROVIDERS = "provider,price per month,deliverability\nPostmark,$15,99.1%\nAmazon SES,$1,97.8%\n";
const CHECKLIST = "# Launch checklist\n\n| Item | Owner | Done when |\n| --- | --- | --- |\n| Analytics | Theo | Page views show in the dashboard |\n| SEO | Maya | Title, description and preview image are set |\n| Status page | Priya | status.fieldnotes.app answers |\n";
const SIGNUP = "export async function signUp(email: string): Promise<Account> {\n  const account = await accounts.create({ email });\n  await mail.send(email, welcomeEmail(account));\n  return account;\n}\n";
// Task ids are known in advance: the CEO creates them in this order, numbered from 1.
const [copy, faq, pricing, provider, signup] = [1, 2, 3, 4, 5];
await script("Maya", "work", [
  [
    tool(
      ["claim_task", { task_id: copy }],
      ["publish_artifact", { name: "landing-copy.md", content: LANDING, purpose: "The landing page's words, for review." }],
      ["complete_task", { task_id: copy, evidence: "landing-copy.md has the headline, three benefits and one call to action." }],
      ["claim_task", { task_id: faq }],
    ),
    say("The copy is in landing-copy.md and ready for review. Starting on the FAQ."),
  ],
]);
await script("Theo", "work", [
  [
    tool(
      ["claim_task", { task_id: pricing }],
      ["publish_artifact", { name: "pricing.html", content: PRICING, purpose: "The pricing table, as a page." }],
      ["complete_task", { task_id: pricing, evidence: "pricing.html shows Free, Pro and Team with monthly prices." }],
    ),
    say("Pricing table published and waiting for review."),
  ],
]);
await script("Priya", "work", [
  [
    tool(
      ["claim_task", { task_id: provider }],
      ["publish_artifact", { name: "providers.csv", content: PROVIDERS, purpose: "Two email providers compared." }],
      ["complete_task", { task_id: provider, evidence: "providers.csv compares Postmark and Amazon SES on price and deliverability." }],
      ["claim_task", { task_id: signup }],
      ["publish_artifact", { name: "signup.ts", content: SIGNUP, audience: "team", purpose: "The sign-up handler, first draft." }],
      ["block_task", { task_id: signup, reason: "Waiting for the chairman to approve the email provider's monthly plan." }],
    ),
    say("Providers compared. The sign-up form waits on the provider approval."),
  ],
]);
const reviews = tool(
  ["review_task", { task_id: copy, ok: true, notes: "Clear headline; the three benefits are concrete." }],
  ["review_task", { task_id: provider, ok: true, notes: "Both providers compared on the same terms." }],
);
await script("Reviewer", "work", [[reviews, say("Reviewed.")], [reviews, say("Reviewed.")]]);

// ---- The CEO breaks the work into tasks for the teams --------------------------------------
const task = (title, goal, success_test, requirement_id, team) => ["create_task", { title, goal, success_test, test_kind: "observable", requirement_id, team }];
await script("CEO", "work", [
  [
    tool(
      task("Write the landing-page copy", "Headline, three benefits and a call to action, in plain words.", "A reader finds the headline, three benefits and one call to action in landing-copy.md.", ids[0], "words"),
      task("Write the FAQ", "Five questions researchers ask before signing up.", "faq.md answers five questions in plain words.", ids[0], "words"),
      task("Build the pricing table", "A responsive table with Free, Pro and Team.", "pricing.html shows three plans with monthly prices.", ids[1], "web"),
      task("Pick the email provider", "Compare two providers on price and deliverability.", "providers.csv lists both with price and deliverability.", ids[2], "backend"),
      task("Wire the sign-up form", "Form, validation and the welcome email.", "A new address gets an account and a welcome email.", ids[2], "backend"),
    ),
    say("Five tasks are on the board: Maya has the words, Theo the pricing table, Priya the sign-up."),
  ],
]);
await post("/v1/chat/command", { ...ref, text: "/do Break the accepted requirements into tasks for the teams." });
await settle(P, "tasks created and worked");
await settle(P, "reviews", 45_000);

// ---- Reviews, an approval and a question for the chairman ----------------------------------
await script("Reviewer", "work", [[tool(["review_task", { task_id: copy, ok: true, notes: "Clear headline; the three benefits are concrete." }]), say("Reviewed the copy.")]]);
await script("CEO", "work", [
  [
    tool(
      ["publish_artifact", { name: "launch-checklist.md", content: CHECKLIST, purpose: "What must be true on launch day." }],
      ["request_approval", { kind: "spend", amount: 15, basis: { kind: "artifact", ref: "providers.csv" }, recommendation: "Approve $15 a month for Postmark so the welcome email reaches inboxes.", if_declined: "We use Amazon SES at $1 a month and accept more emails in spam." }],
      ["ask_question", {
        question: "Should the Team plan show a yearly price as well?",
        why: "A yearly price lifts conversions for teams but adds a row to the pricing table and a decision about the discount.",
        options: ["Monthly only", "Monthly and yearly, 2 months free"],
        recommended: 2,
        default: "Monthly only until you answer.",
        concerns: "other",
      }],
      ["post_heads_up", { text: "The copy passed review. Pricing is ready for review; the sign-up form waits on the email provider approval." }],
    ),
    say("Two things need you: the email provider's monthly plan, and whether Team shows a yearly price. Everything else is moving."),
  ],
]);
await post("/v1/chat/command", { ...ref, text: "/do Review what is done and tell me what needs me." });
await settle(P, "review round");

// ---- A conversation in the chat ------------------------------------------------------------
await script("CEO", "chat", [
  [
    say(
      "Here is where we are:\n\n1. **Copy**: written by Maya, passed review.\n2. **Pricing**: Theo published `pricing.html`; it is waiting for its review.\n3. **Sign-up**: Priya compared providers; the form waits on your approval of Postmark.\n\nWe have used about a third of the budget. At this pace we finish within it.",
      60_000,
    ),
  ],
]);
await post("/v1/chat/send", { ...ref, body: "How is the launch going? Anything you need from me?" });
await settle(P, "chat reply");

const desk = (await get("/v1/desk/show")).waiting.filter((entry) => entry.project_id === P);
const budget = await get(`/v1/budget/show?project_id=${P}`);
log(`done: ${desk.length} waiting on you, ${budget.spent} of ${budget.wall} tokens used`);
log(`open ${base}/projects/${P}`);
writeFileSync(join(runDir, "demo-project.txt"), P);
await api.dispose();
