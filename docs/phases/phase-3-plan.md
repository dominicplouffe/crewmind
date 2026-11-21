# Phase 3 plan: listening

Goal (PLAN.md): the chairman says it once. Pins, decisions, corrections, examples and directives work end to end, and memory recalls.

**Exit demo.**

- The frustration scenarios for theme 1 (doesn't listen) and theme 5 (chat is not command) pass:
  - a standing order ignored;
  - an example used as data;
  - a closed decision re-argued;
  - a question answered sideways;
  - chat acted on without a directive.
- Pinned memory reaches every context pack verbatim (INV-25), checked mechanically.
- Mem0 recall works on both databases.

Status: **draft, waiting for the owner's answers.** The questions are at the end.

## What phase 3 covers

21 requirement ids: CHAT-8, CHAT-11, CHAT-12, CHAT-13; MSG-4 to MSG-8, MSG-12; MEM-1 to MEM-8; INV-23, INV-25, INV-26.

Three of them are partly built already: `/brevity` (CHAT-13), threaded replies with the newest unanswered message first (CHAT-11), and the refusal of state changes from a chat run without a directive (INV-23, part). Phase 3 finishes them.

## Three parts

Each part ends with the suite green on both databases.

| Part | Builds | Demo |
| --- | --- | --- |
| **3a Pinned memory** | Standing orders, closed decisions and reopen requests, corrections, examples, agents' own pinned notes, the caps, and the context pack that carries all of it verbatim. `/pin`, `/unpin`, `/decide`, `/fix`, `/example` and the buttons on messages | Scripted scenarios: an order, a decision and a correction each appear word for word in the next run's context; a re-argued decision is refused |
| **3b Speaking well** | The communication lint with one metered rewrite (MSG-12), the listening score (CHAT-12), the quote-back after `/fix` (CHAT-11), reporting cadence (MSG-8), the example-figure lint (MSG-7) | A long reply is rewritten once; a reply after `/fix` quotes the question; a held status post goes out at the next slot |
| **3c Recall memory** | The memory engine interface, Mem0 behind it on both databases, scopes, extraction after runs and every N chat turns, retrieval into the context pack, the Memory panel, the eval suite | A fact stated in one run is recalled in a later run on SQLite and on Postgres; forgetting removes it |

## What I checked before planning

I installed Mem0 2.2.1 in a scratch environment and read its code. These facts shape the plan.

- **SQLite installs can use Qdrant in embedded mode.** The Qdrant client is already a core dependency of Mem0. It runs in-process and stores to a folder, with no server. This answers spec question Q-001.
- **Keyword-plus-vector search exists on both stores.** Mem0's pgvector store has keyword search; its Qdrant store has BM25 through the `fastembed` library. So MEM-2's hybrid retrieval is met without glue code.
- **Local embeddings without PyTorch.** Mem0 supports `fastembed`, which runs small ONNX models. That fits review item R-52.
- **Extraction can go through our gateway.** Mem0 lets a provider be registered. A small adapter makes Mem0's model calls through the crewmind gateway, so they are metered and no key leaves the server (P3).
- **Mem0 sends telemetry by default.** It must be switched off (`MEM0_TELEMETRY=false`) to keep NFR-1. A test will assert no outbound call.
- **Mem0 keeps its change history in a SQLite file of its own,** even when the vectors are in Postgres. The file will live in the data directory, go into backups, and be purged on forget and on project delete.
- **Mem0 is heavy to load:** 1.8 seconds and about 140 MB. It will be loaded on first use, never at start, so slim mode keeps its start and idle targets (NFR-23).
- **This build environment cannot download an embedding model** (the model hosts are blocked), and its Postgres has no pgvector extension yet. See the questions.

## Modules

```
src/crewmind/
  domain/conversation/
    orders.py          standing orders: propose, confirm, edit, discard, retire (MSG-4, 7.17)
    decisions.py       closed decisions and reopen requests (MSG-5, INV-26, 7.17)
    corrections.py     corrections and the listening score (MSG-6, CHAT-12, 7.17)
    examples.py        example marks and the ILLUSTRATION label (MSG-7)
    standard.py        the communication lint: pure functions (MSG-12)
    cadence.py         reporting slots and the held-post queue (MSG-8)
  domain/memory/
    pinned.py          what is pinned for an agent, sizes against the caps (MEM-1, INV-25)
    engine.py          the narrow interface: add, search, update, forget, history (MEM-2)
    mem0_engine.py     Mem0 behind the interface; store chosen by database
    extraction.py      what to extract and when (MEM-4, MEM-7)
    operations.py      memory.* and agent.* memory operations (MEM-3, MEM-6)
  gateway/
    platform_calls.py  model calls the platform itself makes (extraction, rewrite, order
                       proposal), metered to the project, with the output standard (LLM-15)
  jobs/
    memory.py          extraction after runs; correction expiry; cadence delivery
web/src/panels/        MemoryPanel, pinned records, buttons on messages
```

`domain/execution/context_pack.py` gains the pinned section and the recall section, in the order EXE-15 states.

## Operations

All in the catalog; the surfaces follow from it.

| Operation | Who | Slash |
| --- | --- | --- |
| `orders.propose`, `orders.confirm`, `orders.discard`, `orders.retire`, `orders.list` | Chairman (the CEO may propose) | `/pin`, `/unpin` |
| `decisions.decide`, `decisions.reopen`, `decisions.rule_again`, `decisions.list` | Chairman | `/decide` |
| `agent.request_reopen` | Agent, with evidence newer than the decision | |
| `corrections.record`, `corrections.remove`, `corrections.list` | Chairman | `/fix` |
| `examples.mark`, `examples.unmark` | Chairman | `/example` |
| `memory.search`, `memory.show`, `memory.edit`, `memory.pin`, `memory.forget` | Chairman; observers read | |
| `memory.preferences_show`, `memory.preferences_edit` | Each person, for their own cross-project scope | |
| `agent.note_pinned`, `agent.remember`, `agent.recall` | Agent, within its scopes | |
| `seats.show` gains the listening score | Observers | |

## Tables (migration 0007)

- `standing_orders`: project, text, state, source message, proposed by, confirmed at, retired at.
- `closed_decisions`: project, topic, ruling, state, decided at; `reopen_requests`: decision, agent, evidence links, outcome, at.
- `corrections`: project, agent seat, the message, the chairman's words, the question, state, expires at.
- `example_marks`: project, message or artifact.
- `pinned_notes`: project, seat, text.
- `held_posts`: project, seat, body, due slot.
- `memory_entries`: project, scope kind and id, the engine's id, source link, dates, untrusted flag, pinned flag. The engine holds the text and the index; this table holds what crewmind governs and shows.
- `messages` gains a lint marker (`long`, `unclear`) and the reply's quoted question.

The lifecycles are already in section 7.17 and are added to the drift test.

## Settings used

`memory.pinned_project_tokens`, `memory.pinned_agent_tokens`, `memory.recall_k`, `memory.chat_extract_every`, `decision.reopen_cooldown`, `correction.ttl`, `report.cadence`, `chat.brevity`, `agent.message_words`. All exist in the registry. The fixed numbers the spec states (25 active orders, 400 characters, the word budgets 60, 150 and 400) are constants citing their requirement.

## Tests to write first

1. **INV-25, mechanical:** a property test. For any mix of active orders, closed decisions and live corrections, every context pack built for an agent they concern contains each one's exact text. Retired, expired and removed records are absent or listed as retired.
2. **The five frustration scenarios,** as scripted-harness scenarios with floors:
   - an order is pinned; the next run's pack carries it, and a scripted reply that breaks it is caught by the scenario's check;
   - an example's number never reaches a pack without its ILLUSTRATION label, and the figure lint flags it in a deliverable;
   - an agent that raises a closed topic with no newer evidence is refused; with newer evidence the request reaches the chairman; a second request inside the cooldown is refused;
   - after `/fix`, the next reply quotes the original question;
   - a chat run that tries to change state without citing a directive is refused (already built; the scenario pins it).
3. **Attack tests** for each rule: an agent confirming its own order, retiring an order, reopening a decision itself, reading a scope it does not belong to, writing past the agent cap, or forging a correction.
4. **State tables:** standing order, closed decision, correction, against section 7.17.
5. **Lint unit tests:** each measurable part of MSG-12 as a pure function, table-driven.
6. **Memory engine contract tests,** run against every engine: add, search, update, forget, history, scope isolation. The same tests run on a small in-memory engine (for the fast suite) and on Mem0 with each store.
7. **Recall evals (MEM-8):** scripted project histories with questions and expected facts. A recorded baseline; a drop fails the build.
8. **No telemetry:** with outbound calls recorded, a full memory round trip makes none.

Tests follow the rules added to CLAUDE.md in phase 2: independent, parallel, no real waiting. Mem0 is loaded only by the tests that are about Mem0.

## Review items I plan to apply

These were marked "before phase 3" in `docs/spec-review.md`. Each needs your yes or no (question 6).

| Item | Change |
| --- | --- |
| R-26 | MEM-1 says "Postgres"; it becomes "the project database", so slim mode is covered |
| R-28 | A chairman's pin, fix or decision is never refused by a size cap. It succeeds and opens a flag asking them to retire something. Agent notes are refused at the cap. Lowering a cap below current use is refused with the arithmetic |
| R-23 | A directive that touches a setting only the chairman may change becomes an action card. The chairman confirms it and the change is recorded as the chairman's. The agent never calls the setting operation |
| R-49 | Covered by question 3 |
| R-50 | "A reviewer check flags any figure" becomes a mechanical lint by the platform, not a reviewer seat |
| R-52 | An ONNX embedder, loaded on first use; measured against the slim targets once a model can be downloaded |

## Rules that start in warn-only mode (NFR-20)

None. INV-23, INV-25 and INV-26 are invariants, and the rest guard authority. MSG-12 is feedback by design and never refuses.

## Risks

- **Mem0 is a moving library.** It is pinned to one version behind the narrow interface, with the contract tests as the guard.
- **Real recall quality cannot be measured here** until an embedding model is available. Until then only the plumbing is proven.
- **Extraction costs tokens** on every work run. It uses the fast class and is metered; the scenario suite asserts an idle project still spends nothing (INV-11).

## Questions for the owner

1. **Review stops.** One stop at the full exit demo, as in phase 2, or one after each part?
2. **The embedding model.** MEM-2 says "a bundled open-source model". The small ONNX model is about 130 MB. Should it be downloaded once by `crewmind setup` (needs the network once), or shipped inside the Docker image and fetched on first use elsewhere?
3. **Who writes the one-sentence standing order (R-49)?** Use the chairman's own words when they fit in 400 characters and call a model only to shorten longer ones; or always propose with a model; or never call a model and ask the chairman to shorten.
4. **Testing real recall in this environment.** The model hosts are blocked and Postgres here has no pgvector. May I ask to allow the model host for this environment and install pgvector locally, so recall is tested for real on both databases? Otherwise the real-model evals run only in CI.
5. **Phase 2 leftovers.** Take any of these into phase 3: warm chat sessions (MSG-11), a "load earlier messages" control in the web app, the extractor part of LLM-14 (needed by MEM-4 anyway)?
6. **The review items above** (R-26, R-28, R-23, R-50, R-52): accept all as recommended, or discuss some?
7. **Mem0's own history file.** Accept that Mem0 keeps its change history in a SQLite file in the data directory, on Postgres installs too?
