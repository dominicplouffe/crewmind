### 6.12 Founder: drafting a project in chat (FND)

The Founder is a platform assistant whose only deliverable is a **project spec** (LIB-4). Its doctrine and the goal grammar are product content, kept as one copy served to the Founder, to MCP clients and to human authors.

- **FND-1 Chat.** Drafting happens in the chat (CHAT-1), and the conversation becomes the project chat after creation. It is stored on the server and can be resumed from any surface. Each turn streams. Failures are recorded on the conversation, never lost.
- **FND-2 Tools.** The Founder runs on the platform's drafting model (LLM-14), is metered like every model call but against the install's own account, so it counts against no project budget (INV-8), and has exactly these tools:
  - search roles and crews;
  - list credentials by name;
  - fetch a URL (as untrusted data);
  - read uploads;
  - grade a goal;
  - rehearse a spec;
  - ask questions;
  - propose a spec.
- **FND-3 Draft first, then interview.** Every question carries a recommended answer, and those answers are the draft. A question is one decision, worded so "yes" accepts the recommendation. It offers 2–4 options and says what the answer changes. When more than one credential exists, who pays is asked and never pre-selected.
- **FND-4 Rounds.** Decisions form a tree. By default the Founder asks one decision at a time: the next one whose prerequisites are settled, most load-bearing first. With `grill.pace` \[one at a time\] set to batch, it asks every ready decision in a round. Facts the Founder can look up, it looks up.
  - **Roots:** finish line and the record that settles it; beneficiary and standard; project type; who pays; any date the outside world imposes.
  - **Branches:** budget; anti-metrics; the chairman's role; roster.
  - **Leaves:** quality; authority preset; failure deliverable; resource posture.
- **FND-5 Ledger.** Every settled decision is kept and tagged by source: the chairman's words, an answer, or an assumption. Drafting is done when no unasked decision remains and no assumption would change the draft. The chairman confirms the ledger before creation.
- **FND-6 Goal.** The goal is prose written for the CEO, never a form. Every draft is graded against the goal grammar (FND-7) beside the turn. The grade opens the next turn, and missing elements become questions.
- **FND-7 Goal grammar.** Ten elements, each graded present, weak or missing, with a quoted line and a named fix:
  1. finish line, plus a record the project does not write itself;
  2. beneficiary: who the output must be right for;
  3. standard: a named reference class, and the sentence "the brief is a subset of the standard";
  4. anti-metrics: plausible substitutes that do not count;
  5. method constraints, only where they matter and falsifiable;
  6. stated bias, marked as a bias the project may override on evidence;
  7. quality bar, with a reason and an owner;
  8. the human's role, including what they will **not** do;
  9. resource posture, with a reason and a release condition;
  10. failure deliverable: what is owed if the finish line is missed.

  Elements 1, 3, 4, 7 and 10 are load-bearing: missing any means "not ready". An element that does not apply is graded present with a reason; silence is not accepted. Grading is done by the Founder's model against a fixed rubric with quoted evidence. The rubric's accuracy is tested against reference goals (section 13).
- **FND-8 Dates.** The Founder writes a date only when it is an outside fact (stored with a cited source) or a chairman target (stored as a target, not a pace). Otherwise there is no date. Dates never appear in goal prose, and phases never exist to fill calendar time.
- **FND-9 Roster.**
  - Derived from the goal: find matching roles and crews, then cut to the smallest team that can do the work in parallel. Cut for redundancy, never for timidity.
  - A plan-adversary seat is always staffed on Deliver and Operate. A reviewer seat is staffed whenever independent read is on.
  - The draft states up front which credentials the roster needs.
- **FND-10 Settings.**
  - The Founder sets only what it can justify, with a one-line reason each. It sets the budget (a range, GOV-4) and quality by name, and leaves the other settings at their defaults unless the goal demands otherwise.
  - It drafts Deliver's first requirement as a first usable version (SPD-4), and Explore's bets with short windows (SPD-7).
  - Resource posture is written as a bias with a reason and a release condition, never as a rule that outranks the goal.
- **FND-11 Fire drill.** The Founder rehearses (RHS) the draft before calling it ready, and acts on what the drill finds.
- **FND-12 Quick mode.** On request, the Founder accepts all of its own recommendations and creates and starts the project in under 2 minutes (section 1.3).
  - A quick project gets no data sources, secrets, email or integrations, and one credential pays every seat.
  - Status moves through drafting → creating → starting → started, or failed with nothing created.
  - The ledger goes into the CEO's first context pack.
- **FND-13 After creation.** On every surface: prompt for each missing credential the roster declares, show the setup checklist, and offer to start only when nothing blocks it.
- **FND-14 Doctrine fingerprint.** Each project records a fingerprint of the doctrine it was drafted under. Later doctrine fixes appear as health findings on older projects; they never silently rewrite or block them.
- **FND-15 Grilling a document.** When the brief arrives as an upload or a long paste, the Founder grills it before drafting from it.
  - It extracts the document's content into a list: goals, requirements, constraints, numbers, dates, names, and anything that reads as an example.
  - It turns each of these into a question:
    - a contradiction inside the document;
    - a vague term with no measurable meaning;
    - a number or case that may be an illustration rather than data ("example or real?");
    - a requirement with no way to verify it;
    - a gap against the goal grammar (FND-7).
  - Questions follow FND-3 (one decision, a recommended answer, 2–4 options, what the answer changes) and the order of FND-4, most load-bearing first.
  - Every answer goes into the ledger (FND-5), tagged with the passage it settles. The draft cites which passages became which requirements. Passages the chairman marks as examples are stored as examples (MSG-7).
  - The interview ends only when no extracted item is unresolved. At any point the chairman may say "use your recommendations for the rest"; the remaining recommendations are then accepted and recorded as assumptions.
- **FND-16 Grilling in a running project.** `/grill` makes the CEO run the same interview in the project chat before anything becomes work. It works on a pasted or uploaded document, or on the chairman's last message.
  - Besides the FND-15 checks, the CEO flags every conflict with active standing orders, closed decisions and existing scope, and asks which wins. A ruling that changes a standing order or a decision is recorded through MSG-4 or MSG-5.
  - Grilling questions are chat cards, not decision items: they have no deadline and no default. HUM-4 does not apply, because the chairman asked for them.
  - Nothing from the document becomes a requirement, bet or task until the chairman confirms the resulting ledger. The CEO then proposes it as scope under the usual authority.
  - Other work keeps running during the interview.
  - When a chairman message is long or ambiguous, the CEO may suggest `/grill` with an action card. It never starts a grilling unasked.
