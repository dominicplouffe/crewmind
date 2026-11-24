# Phase 7 plan: Founder and rehearsal (v2.0 release candidate)

Goal (PLAN.md): start a project by talking. A pasted document is grilled before anything is drafted.

**Exit demo.**

- The Founder acceptance scenario passes (section 13):
  - the reference goal grades ready;
  - the raw brief does not, and is missing exactly the elements its hand-graded reference names;
  - quick mode creates and starts a project in under 2 minutes;
  - a document seeded with two contradictions, one illustrative number and one requirement nobody can verify yields a question on each, one at a time, before any draft;
  - the same document grilled in a running project also surfaces its planted conflict with a standing order.
- The full v2.0 acceptance suite passes. The Standards item and the Slack column of surface parity stay in phase 8.

Status: **built on 22 Nov 2026.** The owner's answers and the outcome are at the end.

## What phase 7 covers

28 requirement ids: PRJ-9; IF-4.6, IF-4.7; FND-1 to FND-16; RHS-1 to RHS-4; LIB-1 to LIB-5.

It also finishes what earlier phases left for the Founder: a budget range (GOV-4), seats staffed to match concurrency (SPD-2), the first requirement drafted as a first usable version (SPD-4), promote creating a proper draft (PRJ-7), the gap review against a named standard (WRK-11), the create scope's remaining MCP tools (IF-5.2), and the doctrine and goal grammar served as MCP documents (IF-5.8).

## Five parts

Each part ends with the suite green on both databases.

| Part | Builds | Demo |
| --- | --- | --- |
| **7a Library and spec** | Roles and squads as versioned records, loaded from and exported to files; the starter library; the one project spec format; import, export and clone (LIB-1 to LIB-5, PRJ-9). The phase 2 role stand-in becomes a pinned role version | A project is exported, the export holds no secret value, and importing it gives the same settings, roster and standing orders; clone copies no history |
| **7b Rehearsal** | The fire drill: the real rules, dispatcher and scheduler on a fresh in-memory database with the scripted squad, clocks compressed, and the report (RHS-1 to RHS-4) | A spec with no reviewer hired but independent read on is reported as a staffing finding; the drill spends 0 tokens and refuses any other database |
| **7c The Founder** | The drafting conversation, its eight tools, the decision tree and rounds, the ledger, the goal grammar grader, dates, roster and settings rules, the fire drill before "ready", the doctrine fingerprint (FND-1 to FND-11, FND-14) | A one-paragraph brief becomes a graded draft through questions that each carry a recommendation; who pays is never pre-selected |
| **7d Grilling and quick mode** | Grilling a document before drafting; `/grill` in a running project; quick mode; what happens after creation (FND-12, FND-13, FND-15, FND-16) | The four planted problems each get a question, one at a time; quick mode creates and starts a project; `/grill` finds the conflict with a standing order |
| **7e Surfaces and the acceptance suite** | Drafting in the terminal and the post-creation prompts (IF-4.6, IF-4.7); the Founder in the web app; the create scope over MCP; the reference specs; the full v2.0 acceptance suite as one run | Create, steer, inspect and configure a project three ways: only the app chat, only the CLI, only an MCP client |

## How the Founder is built

- **It is a platform assistant, not a seat.** It runs through the model gateway on the platform drafting model (LLM-14). Its tokens are metered against an install-level account and count against no project budget (R-31).
- **The rules are in code; the model only writes.** The decision tree (roots, branches, leaves), which decision is ready, the ledger and its source tags, "who pays is never pre-selected", "no date without a source", and "drafting is done when no unasked decision remains" are enforced by the platform. The model proposes questions, answers and prose through its tools, and a tool call that breaks a rule is refused, as for any agent (P1).
- **The grade is the model's, the verdict is arithmetic.** The model grades each of the ten elements present, weak or missing, with a quoted line. The platform checks that every quote is in the text, and computes "ready" from the five load-bearing elements.
- **The conversation is an ordinary chat** that becomes the project chat at creation (FND-1). Before creation it belongs to the person.

## What does not exist yet, and what stands in for it

| Later domain | Needed by | Stand-in in phase 7 |
| --- | --- | --- |
| **Agent Skills** (phase 8) | A role's pinned skills (LIB-1); the doctrine published as skills (LIB-6) | The field exists and stays empty. The doctrine and goal grammar are files served to the Founder and over MCP |
| **Data sources, email, integrations** (phase 8) | "Integrations needed" and "controlled domains" in a spec (LIB-4); the setup checklist (FND-13) | The spec carries the fields. The checklist lists them as "not available in this version" |
| **Browser and A2A permissions** (phase 8) | Role tool permissions (LIB-1) | The role carries the permissions; nothing grants a browser or A2A yet |
| **Install history** | Rehearsal's estimate of runs and tokens (RHS-3) | From the squad's reference estimate until an install has finished projects of its own; the report says which it used |

## Modules

This was the plan. What was built differs in places, listed under "Differences from this plan" in the outcome.

```
src/nightsquad/
  domain/library/
    roles.py, squads.py     versioned templates; search
    files.py               load from and export to files
    spec.py                the project spec: one schema, validated
    transfer.py            import, export, clone
    operations.py
  domain/founder/
    tree.py                the decisions, their prerequisites and order
    ledger.py              settled decisions and their sources
    grammar.py             the ten elements, the rubric, the verdict
    grilling.py            extracted items, their questions, what is unresolved
    drafting.py            the conversation: turns, tools, readiness
    quick.py               quick mode and its states
    after.py               missing credentials and the setup checklist
    operations.py, tools.py
  domain/rehearsal/
    drill.py               the run on a fresh in-memory database
    report.py
    operations.py
content/                   roles/, squads/, doctrine/, goal-grammar/, examples/
acceptance/                reference specs, the reference goal, the raw brief, the seeded document
web/src/founder/           the drafting view: question cards, the ledger, the grade
```

## Tables (migration 0014)

`roles`, `role_versions`, `squads`, `founder_conversations`, `founder_decisions` (the ledger), `founder_gradings`, `grill_items`, `rehearsals`; `seats` gains its pinned role version; `projects` gains the doctrine fingerprint and the spec it was created from.

The Founder conversation, quick mode and grilling lifecycles in section 7 are added to the drift test.

## Tests to write first

1. **Spec round trip (LIB-5):** export, import, export again gives the same document, over generated specs; no secret value appears in any export, clone or backup (INV-6).
2. **Rehearsal safety (RHS-1):** the drill makes no network call, runs no command from the spec, reads no credential, sends no alert, and is refused on any database but its own.
3. **The decision tree (FND-4):** over random answer orders, a decision is never asked before its prerequisites, and drafting never ends with an unasked decision or a draft-changing assumption.
4. **The grader's plumbing (FND-7):** a quote not in the text is refused; a missing load-bearing element means "not ready" whatever the model says.
5. **The Founder acceptance scenario,** with a scripted model, in-process and once on a real server for quick mode's two minutes.
6. **Attack tests:** the Founder pre-selecting who pays, writing a date into goal prose, creating before the ledger is confirmed, using a tool it does not have; a grilled document becoming work before the ledger is confirmed; a spec that smuggles a secret value or a role that names a model.

## Review items I plan to apply

| Item | Change |
| --- | --- |
| R-31 | Founder calls get ledger lines against an install-level account: metered, but against no project budget |
| R-32 | One quick-mode target: under 2 minutes |
| R-51 | Rehearsal always runs on a fresh in-memory SQLite database, and the code refuses any other |

## Risks

- **The Founder's quality cannot be proven here.** Tests use a scripted model (owner's decision Q-006: no real-provider test). They prove the rules, the tools and the flow. They do not prove that a real model asks good questions or grades goals accurately.
- **The v1 content needs converting.** 38 roles, 17 squads and 12 example specs are in v1's format: roles name an effort level, and the specs are v1 bundles. Conversion problems go to `docs/spec-questions.md`.
- **Size.** The largest phase so far in new surface: two new domains, a new web view and the full acceptance run.
- **The phase 2 role stand-in is used everywhere.** Replacing it with pinned role versions touches hiring, context packs and lineups.

## Owner answers (22 Nov 2026)

| Question | Answer |
| --- | --- |
| The v1 content | **The owner gives read access to the v1 repository,** and the build imports and converts its roles, squads, doctrine and goal grammar. It is `dominicplouffe/yaaf`; its content was copied into `content/` unchanged on 22 Nov 2026 and is converted in part 7a |
| Proving the grader | **A command the owner runs:** `squad founder eval` grades the reference goals with the owner's own model key and prints agreement with the hand grades. Tests here prove the rules and the flow. FND-7's accuracy clause stays partial until it is run |
| The reference documents | **The build writes them, the owner reviews:** the reference goal with its hand grades, the raw brief, the seeded document and the three reference specs, in `acceptance/` |
| Review items R-31, R-32, R-51 | Accepted as recommended; applied in spec revision 2.18 |
| Review stops | One, at the full exit demo |

No open questions remain.

## Outcome (22 Nov 2026)

Phase 7 is built in its five parts. Of its 28 requirement ids, 16 are done and 12 are partial; `docs/traceability.csv` has the tests and a note for each.

**The one thing to know first: the Founder has never spoken to a real model here.** Every test drives it with a scripted model. The tests prove the rules, the tools, the flow and every surface. They do not prove that a real model asks good questions, drafts a good goal or grades one accurately. Before calling this a release candidate, set `founder.credential`, draft one real project, and run `squad founder eval` (the README has the command).

**Exit demo, item by item.**

| Item | Result |
| --- | --- |
| The reference goal grades ready | Passes, with a scripted grader replaying the hand grade. The platform's part is real: it checks each quote against the goal and computes the verdict |
| The raw brief does not, and is missing exactly the elements its hand grade names | Passes, on the same terms |
| Quick mode creates and starts a project in under 2 minutes | Passes on a real server from the real terminal: 8.8 seconds, of which about 5 are the rehearsal. A real model adds its own thinking time, which was not measured |
| A seeded document yields a question on each planted problem, one at a time, before any draft | Passes. The Founder is refused when it drafts first, asks before listing, or misquotes the document. Finding the four problems is the scripted model's doing; a real model's eye is not tested |
| The same document grilled in a running project surfaces its conflict with a standing order | Passes, on the same terms |
| The full v2.0 acceptance suite passes | See the table below. Two items are not met |

**Section 13, item by item.**

| Item | Where it is tested | State |
| --- | --- | --- |
| Golden path, each type | The three reference specs in `acceptance/` reach their first verified close under the real rules; the phase 5 scenarios cover ready, findings report and cycles | Passes |
| Rule-breaker | Phase 2 scenario | Passes |
| Listening | Phase 3 scenarios and the memory eval | Passes |
| Never silent | Phase 6: all four cases in-process; two on a real server | Passes in part |
| Losing | Phase 5 | Passes |
| Speed | Phase 5, real server | Passes |
| Chaos | Phase 2 chaos tests | Passes |
| Surface parity | Conformance test; the web browser tests; the terminal on a real server; an MCP client with steer and create | Passes for three ways. No single test does create, steer, inspect and configure end to end through one surface alone |
| Multi-provider | Not run. No real provider is called in tests (owner's decision Q-006) | **Not met** |
| Founder | This phase, with a scripted model | Passes as scripted |
| Budget | Phases 2 and 5 | Passes |
| Experience | Accessibility is checked in the browser tests. The section 1.3 timing targets on reference hardware were not measured | **Not met in full** |
| Standards, and the Slack column of parity | Phase 8 | Deferred |
| Slim | Phase 1, real server, both databases | Passes |

**What is true now.**

- A project is one portable file. Import, export, clone, check, rehearse and grade all read it. A spec that carries a credential value is refused, and a spec with any problem creates nothing.
- The library has 41 roles and 17 squads, converted from v1. A role names no model. A team keeps the role version it was hired from until it is re-pinned, and only an admin changes a role that exists.
- A rehearsal runs a spec through the real rules, dispatcher and scheduler in a process of its own that is given the spec and nothing else. Its squad is code, so it spends no tokens and gives the same report each time.
- The Founder acts only through eight tools, and each tool call meets the rules: one question at a time and in order, 2 to 4 options, a recommendation on every question except who pays when the chairman has more than one credential, no date in goal prose, a reason for every setting, a plan adversary on Deliver and Operate. A refused call is kept on the conversation.
- A grade stands only on lines the goal holds. The verdict is computed, not taken from the model.
- A project is created only from a ledger with nothing open, after the draft has been rehearsed. The ledger tells the chairman's words, their answers and assumptions apart, and goes to the CEO in its first run.
- A pasted document is grilled before anything is drafted. In a running project, `/grill` stops the CEO proposing new scope until the chairman confirms the ledger.
- Founder calls are metered against the install and count against no project budget.

**Partial, and why.**

- **A real model (your side).** FND-7's accuracy, and whether the Founder cuts a roster to the smallest team (FND-9), drafts a first usable version (FND-10) or acts well on a rehearsal (FND-11), are the model's judgement and are not checked.
- **No squad has a reference estimate** (LIB-2, GOV-4, Q-013). With no history on the install, the Founder proposes the project type's default budget and says it is a default.
- **Phase 8.** Skills, browser and A2A permissions, integrations and role credentials are carried in roles and specs and grant nothing yet (LIB-1, LIB-4). A document reaches the Founder as text only: no PDF (FND-1).
- **Rehearsal (RHS-3).** Tokens and duration are estimated to the first close, and only once the install has 10 finished runs. A rehearsal does not estimate the whole project.
- **Grilling in a project (FND-16).** The platform checks that a conflict names something that exists; finding the conflicts is the CEO's work. A ruling that changes a standing order is prompted, not applied. The CEO suggesting `/grill` with a card is not built.
- **After creation (FND-13).** The terminal asks for a missing credential; the web shows the checklist but does not ask for the credential in place.
- **A whole spec is not graded** (LIB-5): the goal is.

**Differences from this plan.**

- **The rehearsal's database is a temporary file, not in memory** (review item R-51 said in memory). SQLite in memory cannot serve the dispatcher, the runner and the jobs at once. The file lives in a folder made for the drill and deleted after it, and the code refuses a database that already exists. Recorded in spec revision 2.18.
- **The drill runs one agent at a time,** so the same spec always gives the same report. It does not exercise parallel runs; it reports how much parallelism the roster allows.
- **No `rehearsals`, `founder_gradings` or separate `roles`/`role_versions` tables.** A rehearsal is not stored except with the draft it ran on; roles stay one table with a version column.
- **The drafting conversation and a project's grilling share tables** (`draftings` and its lines, questions, ledger and passages).
- **`squad draft` is the terminal command,** not a subcommand of `founder`; `squad founder eval` is the grader check.
- **Promote now opens a Founder drafting** with the findings report attached, instead of creating a draft project with the report as its goal.

**Things to know.**

- **The v1 content was reworded.** 16 of 38 role charters, the doctrine and the goal grammar named v1 tools, settings and file paths. Two changes are more than rewording: the doctrine's "tempo" section became a short section on the token budget, and one sentence on the reviewer seat was added. The v1 originals are in git history at the import commit. Q-012 to Q-017 in `docs/spec-questions.md` list what was changed, dropped and left for you to decide.
- **Every v1 role named an effort level.** It is dropped; the ten roles v1 ran at its highest level get a floor of the balanced model class.
- **The 12 v1 example projects import at v2 defaults.** Their v1 settings had no exact v2 counterpart, apart from the timezone.
- **Three settings were added** (Q-018): `founder.credential` (none by default, so the Founder does nothing until an admin sets it), `founder.model_class` and `grill.min_characters`; and `rehearsal.max_seconds`.
- **Runs queued at the same instant are now leased in the order their seats were created.** It makes a rehearsal repeatable and changes nothing else.
- **A rehearsal holds SQLite's write lock for about 5 seconds** on a slim install when called as an operation. Postgres is not affected.

**Found and fixed on the way.**

- A model call made inside a tool's transaction deadlocked on SQLite. Grading now happens with no transaction open.
- An operation called from inside another did not run its own preparation step.
- The rehearsal reported a credential as missing that the person had, because the drill's own install has none. It now reports this install's answer.
- Three schema names in the API clashed with older ones and were renamed. Older clashes of the same kind remain; the web types use the long names for them.

**Found and not fixed.**

- **The suite is close to its 10-second limit under load.** One rehearsal test failed once while the browser tests were running beside it. The drill tests now start no process and take about 5 seconds each.
- **An answer of a single letter is always read as an option,** so "a" cannot be given as an answer in the chairman's own words.
- **Refusal hints name CLI commands,** and the web shows them as written.

**Web.** "Start a project" opens a drafting view: the conversation with the Founder's reply streaming in, a question card with the recommended option marked, the ledger, the goal grade, the draft, readiness, and create and start. The Plan panel has a Rehearsal tab; Settings has "Export as a spec" and "Clone". Not covered by a browser test: quick mode, attaching a document, a failed turn, and a question with no recommendation. I did not look at the pages myself; they pass their browser and accessibility tests.

**Tests.** 492 Python tests on SQLite in about 1 minute 45 seconds and on Postgres in about 2 minutes 50 seconds; 8 real-server tests on Postgres in about 2 minutes 35 seconds; 238 web unit tests; 61 browser tests in about 3.5 minutes.

**Open questions for the owner:** Q-012 to Q-018 in `docs/spec-questions.md`. Still on the owner's side: copy `ci/github-actions.yml` to `.github/workflows/`.
