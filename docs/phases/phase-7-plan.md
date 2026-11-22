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

Status: **draft, waiting for the owner's answers.** The questions are at the end.

## What phase 7 covers

28 requirement ids: PRJ-9; IF-4.6, IF-4.7; FND-1 to FND-16; RHS-1 to RHS-4; LIB-1 to LIB-5.

It also finishes what earlier phases left for the Founder: a budget range (GOV-4), seats staffed to match concurrency (SPD-2), the first requirement drafted as a first usable version (SPD-4), promote creating a proper draft (PRJ-7), the gap review against a named standard (WRK-11), the create scope's remaining MCP tools (IF-5.2), and the doctrine and goal grammar served as MCP documents (IF-5.8).

## Five parts

Each part ends with the suite green on both databases.

| Part | Builds | Demo |
| --- | --- | --- |
| **7a Library and spec** | Roles and crews as versioned records, loaded from and exported to files; the starter library; the one project spec format; import, export and clone (LIB-1 to LIB-5, PRJ-9). The phase 2 role stand-in becomes a pinned role version | A project is exported, the export holds no secret value, and importing it gives the same settings, roster and standing orders; clone copies no history |
| **7b Rehearsal** | The fire drill: the real rules, dispatcher and scheduler on a fresh in-memory database with the scripted crew, clocks compressed, and the report (RHS-1 to RHS-4) | A spec with no reviewer hired but independent read on is reported as a staffing finding; the drill spends 0 tokens and refuses any other database |
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
| **Install history** | Rehearsal's estimate of runs and tokens (RHS-3) | From the crew's reference estimate until an install has finished projects of its own; the report says which it used |

## Modules

```
src/crewmind/
  domain/library/
    roles.py, crews.py     versioned templates; search
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
content/                   roles/, crews/, doctrine/, goal-grammar/, examples/
acceptance/                reference specs, the reference goal, the raw brief, the seeded document
web/src/founder/           the drafting view: question cards, the ledger, the grade
```

## Tables (migration 0014)

`roles`, `role_versions`, `crews`, `founder_conversations`, `founder_decisions` (the ledger), `founder_gradings`, `grill_items`, `rehearsals`; `seats` gains its pinned role version; `projects` gains the doctrine fingerprint and the spec it was created from.

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

- **The Founder's quality cannot be proven here.** Tests use a scripted model (owner's decision Q-006: no real-provider test). They prove the rules, the tools and the flow. They do not prove that a real model asks good questions or grades goals accurately. See question 2.
- **The content is not in the repository.** `content/` holds only the output standard; the v1 roles, crews, doctrine and goal grammar were never copied in. See question 1.
- **Size.** The largest phase so far in new surface: two new domains, a new web view and the full acceptance run.
- **The phase 2 role stand-in is used everywhere.** Replacing it with pinned role versions touches hiring, context packs and lineups.

## Questions for the owner

1. **The v1 content.** `content/` has no roles, crews, doctrine or goal grammar, and I cannot reach the v1 repository from here.
2. **Proving the grader.** FND-7 says the rubric's accuracy is tested against reference goals. With no real model in tests, that can only be run by you.
3. **The reference documents.** Section 13 needs a reference goal with a hand-graded grammar, a raw brief, a seeded document and three reference specs. None exist.
4. **Review items R-31, R-32 and R-51.**

Review stops: one, at the full exit demo, as in phase 6, unless you say otherwise.
