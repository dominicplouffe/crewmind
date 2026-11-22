# crewmind v2 build plan

Owner: Dominic. Written 21 Nov 2026 against spec revision 2. Phases follow spec section 13; phase 0 is added before them.

## The cut line

**v2.0 = phases 0–7.** It covers the core, chat and execution, listening, verification, planning and speed, the chairman loop, and the Founder. That is the whole product promise: hand off a goal, stay in control, never repeat yourself.

**Later (phase 8):** Slack, project email and agent mailboxes, A2A, the agent browser, OpenTelemetry export, Agent Skills, extra harnesses, host-jail mode and SSO. The spec keeps these so the v2.0 design leaves room for them, but nobody builds them before phase 7 ships.

v1 grew to about 87,000 lines of Python in seven weeks and failed on structure, not ideas. The cut line, the conformance test and one-phase-at-a-time are what stop that happening again.

## How to work each phase with Claude Code

1. **Plan.** Start a session with "Plan phase N": Claude Code reads the phase's spec files (listed below) and writes `docs/phases/phase-N-plan.md`. The plan covers modules, operations, tables, the tests to write first, and open questions.
2. **Grill the plan.** Run `/grill-me` (or ask Claude Code to interview you) on the plan before code starts.
3. **Build in small changes.** Each change implements a few requirement ids with their tests, on both databases, and updates `docs/traceability.csv`.
4. **Demo and close.** At the end of the phase, run the exit demo below and the phase's acceptance tests, then tick the ids in the matrix. Anything deferred goes in the matrix notes, never silently.

Keep sessions lean: read the three always-read files plus the phase's files, not the whole spec.

## Phase 0: Review and bootstrap

- **Goal:** prove the spec is buildable, and stand up the guardrails before any feature.
- **Spec review:** Claude Code grills the spec and writes `docs/spec-review.md`, covering contradictions, ambiguous or untestable requirements, missing state transitions, settings without a use and uses without a setting. Each item has a recommendation. The owner answers the blocking ones; answers become spec edits plus CHANGELOG lines.
- **Bootstrap:**
  - `uv` project, ruff, pyright strict, pytest with Hypothesis;
  - CI running the suite on SQLite and Postgres;
  - empty operation catalog with the conformance test (IF-1.3) wired to API, CLI and MCP adapters;
  - the attack-test harness;
  - a mock harness stub;
  - the settings registry loaded from Appendix A as data.
- **Exit:** CI green on both databases with the skeleton. The spec review is answered, the conformance test fails when an operation is registered without an adapter, and `crewmind --help` runs.

## Phase 1: Core

- **Goal:** projects exist, are governed by versioned settings, and are reachable from API, CLI and MCP (read).
- **Exit demo:** in slim mode (`crewmind up --slim`) and on a Postgres server, create a user and a project, change a setting with a reason, start, hold and resume it. See every change in the event log from the CLI, the API and an MCP client.
- **Ids:** PRJ-1, PRJ-2, PRJ-3, PRJ-10; ACC-1, ACC-2, ACC-3, ACC-4, ACC-5, ACC-6; INV-5, INV-6, INV-7, INV-21; IF-1.1, IF-1.2, IF-1.3, IF-1.4, IF-3.1, IF-3.2, IF-3.3, IF-3.4, IF-3.5, IF-3.7, IF-3.8, IF-4.1, IF-4.2, IF-4.3, IF-4.4, IF-4.5; IF-5.1 and IF-5.2 in part (see below); BG-1, BG-3, BG-4; NFR-1, NFR-2, NFR-3, NFR-4, NFR-5, NFR-6, NFR-7, NFR-8, NFR-9, NFR-10, NFR-11, NFR-12, NFR-14, NFR-15, NFR-16, NFR-21, NFR-23, NFR-24
- **Partial ids** (spec review R-11):
  - **MCP:** IF-5.1 is delivered here only as minted bearer tokens, and IF-5.2 only as the `read` scope, so the exit demo can use an MCP client. OAuth and the other scopes stay in phase 6.
  - **Extension points:** PRJ-1 start checks, PRJ-2 pause causes, PRJ-3 and PRJ-10 stop and purge hooks, NFR-2 install steps and NFR-5 doctor checks are built as registries. Later phases add their checks (seat check, budget, email, Slack, libraries) without changing project code. Each missing piece is noted in `traceability.csv`.

## Phase 2: Chat and execution

- **Goal:** talk to a CEO in the chat. It runs real work in a sandbox through the model gateway, metered in tokens, and stops at the wall.
- **Exit demo:**
  - In the web app and in `crewmind chat`, the chairman talks to a CEO on the mock harness. A run on a real provider is not part of the test suite (owner decision, Q-006); real providers are covered by recorded responses.
  - An upload becomes an artifact.
  - A run is metered by token kind, and only non-cached tokens count.
  - Hitting the wall pauses the project.
  - Killing a runner mid-run violates no execution invariant.
- **Ids:** CHAT-1, CHAT-2, CHAT-3, CHAT-4, CHAT-5, CHAT-6, CHAT-7, CHAT-9, CHAT-10, CHAT-14, CHAT-16, CHAT-17, CHAT-18, CHAT-19, CHAT-20; LLM-1, LLM-2, LLM-3, LLM-4, LLM-5, LLM-6, LLM-7, LLM-8, LLM-9, LLM-10, LLM-11, LLM-12, LLM-13, LLM-14, LLM-15; GOV-1, GOV-2, GOV-3, GOV-6, GOV-7, GOV-9; ART-1, ART-2, ART-3, ART-4, ART-5, ART-6, ART-7, ART-8, ART-9; MSG-1, MSG-2, MSG-3, MSG-9, MSG-10, MSG-11, MSG-13; EXE-1, EXE-2, EXE-3, EXE-4, EXE-5, EXE-6, EXE-7, EXE-8, EXE-9, EXE-10, EXE-11, EXE-12, EXE-13, EXE-14, EXE-15; INV-4, INV-8, INV-9, INV-11, INV-12, INV-13, INV-15, INV-20, INV-24; IF-3.6, IF-3.9, IF-4.8, IF-6.1, IF-6.2, IF-6.3; BG-2; INT-8
- **Partial ids** (phase 2 plan):
  - **LLM-2, LLM-8:** phase 2 ships API-key credentials, the mock harness and the vendor-neutral harness loop. Subscription logins and the vendor agent SDK harness arrive in phase 8.
  - **EXE-12:** container sandboxes are written here but cannot be run in the build environment, which has no Docker daemon. Their tests skip without one and must pass in CI or on the owner's machine before phase 2 counts as done. The development-only unisolated mode is fully tested.
  - **INT-8:** the Brave Search API is the first search service.
  - **No tasks yet:** tasks belong to phase 4, so the task-related wake triggers (EXE-2) and the work group of the agent API (IF-6.3) arrive there.
- **Review:** one stop, at the exit demo. The work is still built in four parts (execution core, models, conversation, web app), each with the suite green on both databases.
- **Web app:** the whole chat bar, including audio and video previews, the installable phone app with push, the command palette, version compare and full-text search.

## Phase 3: Listening

- **Goal:** the chairman says it once. Pins, decisions, corrections, examples and directives work end to end, and memory recalls.
- **Exit demo:** the frustration scenarios for theme 1 (doesn't listen) and theme 5 (chat is not command) pass. Pinned memory reaches every context pack verbatim (INV-25), and Mem0 recall works on both databases.
- **Ids:** CHAT-8, CHAT-11, CHAT-12, CHAT-13; MSG-4, MSG-5, MSG-6, MSG-7, MSG-8, MSG-12; MEM-1, MEM-2, MEM-3, MEM-4, MEM-5, MEM-6, MEM-7, MEM-8; INV-23, INV-25, INV-26; plus the rest of MSG-11 (warm chat sessions) and the extractor part of LLM-14, carried from phase 2

## Phase 4: Verification

- **Goal:** "done" means checked by something other than the doer.
- **Exit demo:** the rule-breaker acceptance scenario passes. A test that passes before any work is refused, and a launch without a watch is refused.
- **Ids:** WRK-1, WRK-2, WRK-3, WRK-4, WRK-5, WRK-6, WRK-7, WRK-8, WRK-9, WRK-12, WRK-13, WRK-14, WRK-15, WRK-16, WRK-17; INV-1, INV-2, INV-3, INV-14, INV-16; EXE-16; the spinning guard of GOV-7

## Phase 5: Planning and speed

- **Goal:** the three project types, honest projections, and speed as a requirement.
- **Exit demo:** the golden path passes for all three types, and the speed acceptance criterion passes. A nearly finished Deliver project draws the CEO reserve, and a half-finished one is refused.
- **Ids:** PRJ-4, PRJ-5, PRJ-6, PRJ-7, PRJ-8; SPD-1, SPD-2, SPD-3, SPD-4, SPD-6, SPD-7, SPD-8, SPD-9; GOV-4, GOV-5, GOV-10; PLN-1, PLN-2, PLN-3, PLN-4, PLN-5, PLN-6, PLN-7, PLN-8, PLN-9, PLN-10, PLN-11, PLN-12; INV-18, INV-19; WRK-11 (moved from phase 4: it needs requirements)

## Phase 6: Chairman loop

- **Goal:** the chairman sees everything that matters and is never left in silence.
- **Email:** alerts and briefs go by browser push and in the app. The install's outbound mail account moved to phase 8 with project mailboxes (owner, 22 Nov 2026).
- **Exit demo:** the never-silent acceptance scenario passes. The desk, daily brief, since-you-were-away, agenda and alerts all agree with the event log, and MCP steer and create scopes work with two-phase confirmation.
- **Ids:** CHAT-15; GOV-8; HUM-1, HUM-2, HUM-3, HUM-4, HUM-5, HUM-6, HUM-7, HUM-8, HUM-9, HUM-10, HUM-11, HUM-12; INT-7; INV-10, INV-17, INV-22; IF-5.1, IF-5.2, IF-5.3, IF-5.4, IF-5.5, IF-5.6, IF-5.7, IF-5.8; NFR-13; WRK-10 (moved from phase 4: it needs decision items); SPD-5 (moved from phase 5: it needs question items)

## Phase 7: Founder and rehearsal (v2.0 release candidate)

- **Goal:** start a project by talking. A pasted document is grilled before anything is drafted.
- **Includes:** importing v1 content from `content/` (roles, crews, doctrine, goal grammar).
- **Exit demo:** the Founder acceptance scenario passes, grilling included. The full v2.0 acceptance suite passes; the Standards item and the Slack column of surface parity are deferred.
- **Ids:** PRJ-9; IF-4.6, IF-4.7; FND-1, FND-2, FND-3, FND-4, FND-5, FND-6, FND-7, FND-8, FND-9, FND-10, FND-11, FND-12, FND-13, FND-14, FND-15, FND-16; RHS-1, RHS-2, RHS-3, RHS-4; LIB-1, LIB-2, LIB-3, LIB-4, LIB-5

## Phase 8: Breadth (after v2.0)

- **Order:** project email (managed via Stalwart, manual, agent mailboxes), then the agent browser, OpenTelemetry export, Agent Skills, A2A, Slack, extra harnesses, host-jail mode, TOTP and SSO.
- **Exit:** the remaining acceptance items pass, Standards and Slack parity included.
- **Ids:** EXE-17; LIB-6; INT-1, INT-2, INT-3, INT-4, INT-5, INT-6, INT-9, INT-10, INT-11; ACC-7; IF-7.1, IF-7.2; NFR-22

## Cross-cutting ids

These apply in every phase and are checked continuously: P1, P2, P3, P4, P5, P6, P7, P8, P9, P10, P11, P12, P13, P14, P15, P16, P17, P18; NFR-17, NFR-18, NFR-19, NFR-20

## Risks to watch

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Scope creep | v1's failure mode | Cut line above; phase exit demos; traceability matrix |
| SQLite and Postgres drift | v1's tests described a database nobody deployed | Both in CI from phase 0; storage adapter; no database-specific logic in domain code |
| Non-cached token counting | Providers report cache usage differently; budgets depend on it | Gateway normalises usage fields per provider with tests from recorded responses (phase 2) |
| Mem0 on SQLite | Embedded vector store choice is open (spec question Q-001) | Decide in phase 3 plan; recall evals on both databases |
| Web chat quality | Section 5 sets a coding-assistant bar | Design the chat in phase 2 against CHAT-1 to CHAT-20 and NFR-17 latency targets; owner review at the phase 2 demo |
| Refusal loops | v1 agents fought refusals | Warn-only mode for new rules (NFR-20); refusal-rate dashboard from phase 2 |
