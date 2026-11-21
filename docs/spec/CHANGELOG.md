# Spec changelog

Newest first. One line per change, citing the ids touched.

## Revision 2.5 (21 Nov 2026): phase 1 build

- **7.8:** the first admin is created in the invited state with a setup link, like any invite, not directly as active. This matches NFR-2 ("creates the first admin and prints a setup link").
- **7.11:** in a break-glass hand-on, a person who is not yet a member joins as a co-chair first, so an admin can replace a chairman who was the project's only member.

## Revision 2.4 (21 Nov 2026): phase 1 plan answers

- **ACC-5, 7.8:** deactivating a person who chairs a project is refused, naming the projects. An admin hands each chair on first.
- **PLAN.md, traceability.csv:** INV-4 and BG-2 move to phase 2, where runs and the dispatcher exist.

## Revision 2.3 (21 Nov 2026): phase 0 bootstrap

- **IF-1.3:** an operation belongs on the `slash` surface only when it declares a slash command, and a host-local operation belongs on `cli` only. This matches IF-1.1 ("its chat slash command, if any") and IF-4.2.

## Revision 2.2 (21 Nov 2026): plain, short output from every model call

- **P18, LLM-15 (new), MSG-12, Appendix A:**
  - Every model call the platform makes or prepares carries one output standard: plain English, the answer first, no padding.
  - Length is spent only where the task asks for it.
  - A test fails if any prompt-building path omits the standard.
  - Agent-to-agent messages and notes get a length budget, `agent.message_words` \[150\].
  - Measured and fed back, never refused (P1). LLM-15 is in phase 2.

## Revision 2.1 (21 Nov 2026): phase 0 spec review answers

Owner answers to the blocking items in `docs/spec-review.md`.

- **P5, WRK-6, INV-3, 7.3:** a solo project with independent read off may self-report observable-test tasks only. The exemption is now written into P5; command tests always need the platform check (R-01).
- **GOV-3, PRJ-2, EXE-9, 7.7, 9.2, section 13:** at the budget wall, in-flight runs finish within `run.max_tokens` and nothing new is leased. A hold, a kill, the refusal cap and every other pause still revoke at once (R-02).
- **7.1, PRJ-2:** projects carry a set of hold reasons (`chairman`, `budget_wall`, `auth_failures`, `skipped_cycles`), each lifted by its own trigger. `/resume` is refused while the wall holds (R-03).
- **Section 3, section 7, ACC-5:**
  - "Chairman" in a Who column means the chairman or a co-chair, except for delete and hand-on.
  - Instance roles are `admin` and `member`; any active person may create a project and becomes its chairman.
  - On hand-over, the previous chairman becomes a co-chair (R-04).
- **NFR-10:** current state lives in tables. Each change writes its event in the same transaction. Reports come from the log or from rebuildable read models, and frozen snapshots are events (R-05).
- **IF-1.2, IF-1.3:** `agent_api` is a catalog surface. Operations declare their principals, and surfaces not yet built are exempt as a whole, with their phase named (R-06).
- **IF-4.2:** install, `up`, update and `migrate --to postgres` join the host-local commands (R-07).
- **Section 7:**
  - New tables cover accounts, single-use links, sessions and tokens, MCP confirm tokens, membership, teams and seats, cycles, artifact locks, evidence, side effects and watches, directives, action cards, standing orders, closed decisions, corrections, threads, chat sessions, suggestions and notices, model credentials, circuit breakers, tool permissions, mailboxes, drafting conversations and skill versions.
  - New rows: platform defaults for proposed scope and commitments, cycle-roll reopening, platform blocking and killing of tasks, the chairman moving a commitment date, leased runs that never start, and flag, heads-up and mistake-report states.
  - A lifecycle missing from section 7 must not be implemented.
  - New interpretations to confirm in the phase plans: a seat is paused when its seat check fails; the artifact status label is derived on read, not stored (R-08).
- **7.1, EXE-5:** a matrix states which run kinds may lease in each project state (R-09).
- **GOV-1, Appendix A, section 3, ACC-3, PRJ-8, HUM-11, GOV-2:**
  - New settings: `authority.preset` (with `custom`) and the six `authority.*` verb settings; `project.timezone` and `person.timezone`; `cycle.period`, `cycle.roll_day` (0 = Monday) and `cycle.due_time`; `token.default_expiry`.
  - GOV-1 rules now differ by scope.
  - Appendix A gains a Constraints list and an Operational settings table. The port, data directory and sandbox ranges there are starting defaults (R-10).
- **PLAN.md, traceability.csv:**
  - PRJ-9, IF-4.6 and IF-4.7 move to phase 7.
  - Phase 1 takes minted MCP bearer tokens and the `read` scope from IF-5.1 and IF-5.2.
  - PRJ-1, PRJ-2, PRJ-3, PRJ-10, NFR-2 and NFR-5 are built as extension points (R-11).

## Revision 2 (21 Nov 2026)

- **Renamed** the project from yaaf to crewmind: product, package, CLI, environment variables, Slack and mail prefixes (ADR-0008).
- **Full rewrite from revision 1:** chat-first front door (CHAT); token-only budgets with the budget as the wall and a CEO reserve (GOV-2, GOV-3, GOV-10); speed requirements (SPD); one quality dial (LLM-3); mailbox per project, managed (Stalwart) or manual, with per-agent accounts (INT-6, INT-10); Mem0 recall memory with an exact pinned layer (MEM); every file an artifact (ART); grilling (FND-15, FND-16); Agent Skills (LIB-6); agent browser (EXE-17); A2A (INT-11); OpenTelemetry export (NFR-22); slim mode on SQLite (NFR-23); Python stack (NFR-24); state machines (section 7); settings registry (Appendix A).
- **Owner decisions recorded:** Python; Postgres and SQLite; budgets count non-cached tokens only; Mem0; separate mailbox accounts per agent; subscription logins are the user's choice. See `docs/decisions/`.
- **Removed:** tempo and bar presets, stakes, dollar model budgets, run-count allowances and inbox lanes, the global plan gate, measurement windows, the change stamp, directives inferred from chat, the budget overage multiple.
