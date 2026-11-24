### 6.12 Founder: drafting a project in chat (FND)

The Founder is a platform assistant whose only deliverable is a **project spec** (LIB-4). Its doctrine and the goal grammar are product content, kept as one copy served to the Founder, to MCP clients and to human authors.

- **FND-1 Chat.** Drafting happens in the chat (CHAT-1), and the conversation becomes the project chat after creation. It is stored on the server and can be resumed from any surface. Each turn streams. Failures are recorded on the conversation, never lost. Before the project exists the conversation is kept as its own record; at creation its lines are copied into the project chat in order. A document is attached to it as text. Every tool call of the Founder that a rule refuses is kept on the conversation, with the rule.
- **FND-2 Tools.** The Founder runs on the platform's drafting model (LLM-14), is metered like every model call but against the install's own account, so it counts against no project budget (INV-8), and has exactly these tools:
  - search roles and squads;
  - list the model credentials and the connections the chairman can attach, by name and description (CON-14);
  - fetch a URL (as untrusted data);
  - read uploads;
  - grade a goal;
  - rehearse a spec;
  - ask questions;
  - propose a spec.
- **FND-3 Draft first, then interview.** Every question carries a recommended answer, and those answers are the draft. A question is one decision, worded so "yes" accepts the recommendation. It offers 2–4 options and says what the answer changes. When more than one credential exists, who pays is asked and never pre-selected.
- **FND-4 Rounds.** Decisions form a tree. By default (`grill.pace` \[batch\]) the Founder asks every decision whose prerequisites are settled in one round, most load-bearing first, each as its own question with its own recommended answer. The chairman answers the round, and the Founder takes its next turn after the last answer. Set to one at a time, it asks only the next decision. A goal that has not changed is not graded again. Once a draft exists, the Founder changes it by sending only the fields that differ, and each draft is rehearsed as it is kept (FND-11). Facts the Founder can look up, it looks up. Who pays is looked up, not asked, when the chairman has one credential or none.
  - **Roots:** finish line and the record that settles it; beneficiary and standard; project type; who pays; any date the outside world imposes.
  - **Branches:** budget; anti-metrics; the chairman's role; roster.
  - **Leaves:** quality; authority preset; failure deliverable; resource posture.
- **FND-5 Ledger.** Every settled decision is kept and tagged by source: the chairman's words, an answer, or an assumption. Drafting is done when no unasked decision remains and no assumption would change the draft. The chairman confirms the ledger before creation. A draft is ready when no question and no passage is open, every decision of the tree is in the ledger, the goal grades ready, and the draft as it stands has been rehearsed and reached its first close. Creating the project is the chairman confirming the ledger, and is refused before then. An assumption never replaces the chairman's words or an answer.
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

  Elements 1, 3, 4, 7 and 10 are load-bearing: missing any means "not ready". An element that does not apply is graded present with a reason; silence is not accepted. Grading is done by the Founder's model against a fixed rubric with quoted evidence. The platform checks the grade before it stands: each element is graded once; a quoted line must be in the goal; weak needs a quoted line; present needs a quoted line or the reason the element does not apply; weak and missing need a named fix. The verdict is computed from the grades, not taken from the model. The rubric's accuracy is tested against reference goals (section 13). 
- **FND-8 Dates.** The Founder writes a date only when it is an outside fact (stored with a cited source) or a chairman target (stored as a target, not a pace). Otherwise there is no date. Dates never appear in goal prose, and phases never exist to fill calendar time. A proposed goal whose prose holds a calendar date is refused.
- **FND-9 Roster.**
  - Derived from the goal: find matching roles and squads, then cut to the smallest team that can do the work in parallel. Cut for redundancy, never for timidity.
  - A plan-adversary seat is always staffed on Deliver and Operate. A reviewer seat is staffed whenever independent read is on.
  - The draft states up front which credentials and connections the roster needs, which the chairman has, and drafts their grants (CON-14).
- **FND-10 Settings.**
  - The Founder sets only what it can justify, with a one-line reason each. It sets the budget (a range, GOV-4) and quality by name, and leaves the other settings at their defaults unless the goal demands otherwise.
  - It drafts Deliver's first requirement as a first usable version (SPD-4), and Explore's bets with short windows (SPD-7).
  - Resource posture is written as a bias with a reason and a release condition, never as a rule that outranks the goal.
- **FND-11 Fire drill.** Every draft is rehearsed (RHS) as soon as it is kept, without the Founder asking, and the Founder acts on what the drill finds. The Founder may also ask for a rehearsal itself.
- **FND-12 Quick mode.** On request, the Founder accepts all of its own recommendations and creates and starts the project in under 2 minutes (section 1.3). A quick draft is still rehearsed before the project is created. Creating and starting are one step: if either fails, nothing is created and the conversation ends failed.
  - A quick project gets no data sources, secrets, email or integrations, and one credential pays every seat.
  - Status moves through drafting → creating → starting → started, or failed with nothing created.
  - The ledger goes into the CEO's first context pack.
- **FND-13 After creation.** On every surface: prompt for each missing model credential and each open need of the roster (secrets, variables, MCP servers; CON-5), show the setup checklist, and offer to start only when nothing blocks it, or to start without what is missing with the dependent seats held (CON-5).
- **FND-14 Doctrine fingerprint.** Each project records a fingerprint of the doctrine it was drafted under. Later doctrine fixes appear as health findings on older projects; they never silently rewrite or block them.
- **FND-15 Grilling a document.** When the brief arrives as an upload or a long paste, the Founder grills it before drafting from it. A long paste is one of at least `grill.min_characters` \[1,500\]. Each extracted item quotes the document word for word, or it is refused. Passages marked as examples reach the CEO labelled as examples, with the ledger.
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
- **FND-16 Grilling in a running project.** `/grill` makes the CEO run the same interview in the project chat before anything becomes work. It works on a pasted or uploaded document, or on the chairman's last message. One grilling is open in a project at a time. While it is open the CEO may propose no requirement and open no bet; the chairman may still add scope, and work under existing scope goes on. A conflict the CEO lists names the standing order, closed decision or requirement it conflicts with, which must exist.
  - Besides the FND-15 checks, the CEO flags every conflict with active standing orders, closed decisions and existing scope, and asks which wins. A ruling that changes a standing order or a decision is recorded through MSG-4 or MSG-5.
  - Grilling questions are chat cards, not decision items: they have no deadline and no default. HUM-4 does not apply, because the chairman asked for them.
  - Nothing from the document becomes a requirement, bet or task until the chairman confirms the resulting ledger. The CEO then proposes it as scope under the usual authority.
  - Other work keeps running during the interview.
  - When a chairman message is long or ambiguous, the CEO may suggest `/grill` with an action card. It never starts a grilling unasked.
