# Spec review (phase 0)

Reviewed: spec revision 2 (all of `docs/spec/`), `docs/PLAN.md`, `docs/decisions/`, `docs/traceability.csv`. Date: 21 Nov 2026.

How to read this:

- Each item has an id (`R-nn`), the spec reference, a quote, the problem, and a recommended fix.
- **Blocking** items must be decided before phase 1 starts. They are listed first and are the subject of the owner interview.
- Every other item is tagged with the phase it must be settled before (**before phase N**). Those go to the phase plan that first touches them; nothing below is decided by this document alone.
- Mechanical checks that came back clean: every requirement id appears in the spec, in `PLAN.md` and in `traceability.csv` exactly once; every setting in Appendix A is cited by at least one requirement, and every backticked setting in the requirements exists in Appendix A.

## Owner answers (21 Nov 2026)

All blocking items are decided and applied to `docs/spec/` (CHANGELOG revision 2.1), `docs/PLAN.md` and `docs/traceability.csv`.

| Item | Answer |
| --- | --- |
| R-01 | As recommended: P5 carries the solo exemption, for observable tests only |
| R-02 | **Not as recommended.** At the budget wall, in-flight runs finish within `run.max_tokens`; this applies to the wall only. Hold, kill, the refusal cap and every other pause still revoke |
| R-03 | As recommended: a set of hold reasons, each lifted by its own trigger |
| R-04 | As recommended |
| R-05 | As recommended: state tables plus a transactional event log |
| R-06 | As recommended |
| R-07 | As recommended |
| R-08 | **Broader than recommended:** every missing lifecycle is drafted in section 7 now. The R-53, R-57, R-58, R-59 and R-60 fixes are applied as part of that. R-54, R-61 and R-62 stay open |
| R-09 | As recommended |
| R-10 | As recommended (all three parts) |
| R-11 | As recommended |

The non-blocking items below stay open and go to the plan of the phase each one names.

## Summary

| Category | Blocking | Non-blocking |
| --- | --- | --- |
| 1. Contradictions | R-01, R-02, R-03, R-04 | R-20 to R-33 |
| 2. Ambiguous or untestable | R-05, R-06, R-07 | R-34 to R-52 |
| 3. State transitions | R-08, R-09 | R-53 to R-62 |
| 4. Settings | R-10 | R-63 to R-66 |
| 5. Phase dependencies | R-11 | R-67 to R-74 |

---

## Blocking items (decide before phase 1)

### R-01 Solo self-reporting contradicts P5

- **Ref:** P5; WRK-6; INV-3; section 7.3.
- **Quote:** P5: "Nobody grades their own work. … Completion requires a platform-run check, outside evidence the platform verifies, or a reviewer who is not the author." WRK-6: "in a solo project with independent read off → done, labelled 'self-reported'." INV-3: "Solo projects are exempt and labelled."
- **Problem:** Principles override everything (section 0), and P5 has no solo exemption. An invariant may only restate a requirement, yet INV-3 and WRK-6 carve out an exception the principle forbids. As written, a conforming build cannot ship WRK-6.
- **Recommendation:** Amend P5 to carry the exemption explicitly: "A solo project with independent read off may close observable-test tasks as self-reported. They are labelled as such everywhere (WRK-15), and command tests still need the platform check (INV-2)." Also restrict the 7.3 row `claimed → done` to observable tests (see R-56).

### R-02 GOV-3 lets in-flight runs finish at the wall; everything else revokes them

- **Ref:** GOV-3; PRJ-2; EXE-9; 7.7; section 13 "Budget".
- **Quote:** GOV-3: "In-flight runs finish, each bounded by its per-run cap. The project pauses." PRJ-2: "Pausing revokes live work-run tokens and purges queued work runs." EXE-9: "Kill, hold, pause, the wall and the refusal cap all revoke the run token." Section 13: "the project pauses within one scheduler tick, live tokens stop working".
- **Problem:** Two opposite behaviours at the wall. Revocation is a phase 2 feature, but the pause semantics belong to the 7.1 lifecycle built in phase 1.
- **Recommendation:** Revoke. At the wall, the platform pauses the project and revokes live work-run tokens. Overspend is bounded by model calls already accepted by the gateway, which INV-9 already allows. Reword GOV-3: "In-flight runs are revoked; model calls already in progress complete and are metered."

### R-03 Paused has several causes, but 7.1 has one undifferentiated resume

- **Ref:** 7.1; PRJ-1; PRJ-2; GOV-3; GOV-10; LLM-11.
- **Quote:** 7.1: "held, paused → running | `/resume`; the resume time arrives; Operate budget reset". PRJ-1: "Start is refused … for projects whose budget is spent". GOV-3: "An Operate project paused at the wall resumes automatically into one new cycle."
- **Problem:**
  - `/resume` on a project paused at the wall would lease into an exhausted budget, breaking INV-9. PRJ-1 refuses *start* when the budget is spent, but says nothing about *resume*.
  - Raising the budget does not say whether it lifts a wall pause.
  - "Operate budget reset" would resume a project paused for 2 skipped cycles or for authentication failures, not only for the wall.
  - A held project still allows chat runs, which spend tokens. If chat crosses the wall while held, there is no `held → paused` transition.
  - Two causes can hold at once (held by the chairman and at the wall). The table has no way to represent that.
- **Recommendation:** Model the cause separately from the state. A project keeps its 7.1 state, plus a set of active **hold reasons**: `chairman` (with an optional lift time), `budget_wall`, `auth_failures`, `skipped_cycles`. The project is `held` when only `chairman` is present, `paused` when any platform reason is present, and `running` when the set is empty. Each reason is lifted by its own trigger:
  - `chairman`: `/resume` or the lift time;
  - `budget_wall`: a budget raise, a reserve draw, or the Operate monthly reset;
  - `auth_failures`: a successful credential check, or `/resume` after the credential is fixed;
  - `skipped_cycles`: `/resume`.

  `/resume` is refused while `budget_wall` holds, with the arithmetic (GOV-9). Add these rules to 7.1.

### R-04 Who "Chairman" means in section 7 and in authority checks

- **Ref:** Section 3 (co-chair); 7.1 to 7.6 "Who" columns; 7.5; GOV-1; ACC-5.
- **Quote:** Section 3: co-chair may "Act as the chairman, except handing on the chair and deleting the project". 7.5: "Chairman or co-chair". 7.1: "Chairman" throughout.
- **Problem:** 7.5 names co-chairs explicitly while the other tables do not, which suggests co-chairs are excluded elsewhere. The phase 1 authority checks for start, hold and resume depend on the answer. Related gaps:
  - The spec never says who may create a project.
  - Instance roles are only implied: the CLI "promote or demote" and the admin row in section 3.
  - It never says what the previous chairman becomes after handing on the chair.
- **Recommendation:**
  - Add a definition to section 7: "Chairman" in a Who column means the chairman or a co-chair, except for deleting a project and handing on the chair.
  - Define two instance roles in ACC: `admin` and `member`. Any active member may create a project and becomes its chairman.
  - On hand-over, the previous chairman becomes a co-chair.
  - Admin break-glass hand-over is recorded as a distinct actor.

### R-05 Event log versus current state

- **Ref:** NFR-10; INV-21; HUM-9; PRJ-4; PRJ-8; NFR-17.
- **Quote:** NFR-10: "Reports are derived from the append-only event log when read; a computed summary is never stored as the truth." HUM-9: "It holds a frozen snapshot of the numbers". NFR-17: "app reads under 300 ms at p95 for a project with 100,000 events".
- **Problem:** The text supports two readings: full event sourcing, or state tables plus an audit log. Receipts, scorecards and review snapshots are stored summaries. The 300 ms target over 100,000 events rules out folding the log on every read. This is the core storage decision of phase 1.
- **Recommendation:**
  - Current state lives in normal tables. Each state change writes its typed event (before, after, actor) in the same transaction (INV-21).
  - Reports and feeds are computed from events, or from read models that can be rebuilt from events and are never edited by hand.
  - Frozen snapshots (receipt, scorecard, status review) are themselves events: point-in-time records, never "the truth" about the present.
  - Reword NFR-10 to say this.

### R-06 Is the agent API a catalog surface?

- **Ref:** IF-1.2; IF-1.3; P11; CLAUDE.md "One operation, one implementation".
- **Quote:** IF-1.2: "HTTP routes, CLI commands, MCP tools, slash commands and Slack actions are thin adapters". P11 and CLAUDE.md also list the agent API.
- **Problem:** The phase 0 conformance test needs a fixed list of surfaces and a rule for which operations belong on which. Agent operations (claim, complete, file evidence) are not human operations, and human-only operations never appear on the agent API.
- **Recommendation:**
  - Surfaces are `api`, `cli`, `mcp`, `slash`, `slack` and `agent_api`. Each operation declares the principals it serves (person, MCP client, agent run).
  - The conformance test checks each operation against every surface its principals reach, unless the operation carries a written exemption.
  - Surfaces not yet built (slash commands and Slack before their phases) are exempt as a whole, with the phase named, so the test still fails on a missing adapter of a built surface.
  - Add `agent_api` to IF-1.2.

### R-07 Host-local commands beyond the IF-4.2 list

- **Ref:** IF-4.2; NFR-2; NFR-3; NFR-23.
- **Quote:** IF-4.2: "bootstrap the first admin or issue a password-reset link, backup, restore, master-key rotation. Nothing else may bypass the API."
- **Problem:** `squad up --slim` (start the server and migrate), the install command (NFR-2), `update` (NFR-3) and `migrate --to postgres` (NFR-23) all touch storage directly, but none is on the list. Read literally, they are forbidden.
- **Recommendation:** Extend IF-4.2's list to: install, `up` (start, including migrate-on-start), update, `migrate --to postgres`, bootstrap admin, password-reset link, backup, restore, master-key rotation. Each is marked host-local in the catalog and exempt from the API, MCP and Slack surfaces.

### R-08 Section 7 is missing most lifecycles

- **Ref:** Section 7 intro: "Every lifecycle is declared once, here. A transition not listed is refused." CLAUDE.md: "Lifecycles come from the tables in `docs/spec/07-state-machines.md`."
- **Problem:** Many stateful concepts have states in the requirements but no table:
  - **Phase 1:** person account (active, deactivated, locked out, ACC-1); invite and reset link (unused, used, expired, ACC-4); personal token and MCP token (active, expired, revoked, ACC-3); membership (ACC-5).
  - **Later:**
    - Seat (active, paused, stood down; nothing ever pauses a seat) and team (stood down, recalled).
    - Cycle (open, then completed, missed or skipped).
    - Flag (open, raised, acknowledged, cleared; HUM-6).
    - Artifact status (draft, in review, verified, delivered).
    - Evidence (pending, verified, failed).
    - Side effect (declared, finished).
    - Watch, directive and action card.
    - Standing order (active, retired) and correction (active, expired).
    - Circuit breaker (closed, open, half-open).
    - Quick-mode status (drafting, creating, starting, started, failed; FND-12).
    - Skill version review (LIB-6).
    - MCP confirm token (IF-5.3).
    - Mailbox (INT-6).
- **Recommendation:** Keep the rule. Add the phase 1 tables now (account, link, token, membership). Add the requirement that each later phase adds its tables to section 7 in its plan, before code. Note in the section 7 intro that a lifecycle missing from section 7 must not be implemented.

### R-09 Paused or held project with chat and directives: which run kinds may lease in each state

- **Ref:** PRJ-2; PRJ-5; GOV-3; EXE-5; 7.7; MSG-3; INV-20.
- **Quote:** PRJ-2: "The chairman can still chat." EXE-5: "Runs for projects that are no longer running are dropped". GOV-3: "nothing new is leased, including chat runs".
- **Problem:** No single rule says which run kinds lease in each project state. EXE-5 would drop chat runs on a held project, which contradicts PRJ-2. The states draft, ready and completed are not covered at all. Phase 1 builds the states and phase 2 builds leasing, so the matrix must exist before the 7.1 implementation sets its guards.
- **Recommendation:** Add a lease matrix to 7.1:

| State | Work runs | Chat runs | Check runs |
| --- | --- | --- | --- |
| draft | no | no (Founder chat is not a project run) | no |
| running | yes | yes | yes |
| held | no | yes | no |
| paused (wall) | no | no; status card instead | no |
| paused (other) | no | yes | no |
| ready | no | yes (PRJ-5) | no |
| completed | no | yes | no |
| stopped, deleting | no | no | no |

  Reword EXE-5 as "runs whose kind the project state does not allow are dropped".

### R-10 Settings that are used but missing from Appendix A, and the scope of GOV-1

- **Ref:** Section 3 (authority dial); NFR-8; GOV-2; HUM-11; HUM-12; PRJ-8; ACC-3; NFR-7; GOV-1; Appendix A.
- **Quote:** Section 3: "Six per-project settings decide who holds each delegable verb". GOV-2: "per calendar month (project timezone)". ACC-3: "expire after 1–365 days (default 30)". GOV-1: "Each change needs a reason of at least 10 characters".
- **Problem:** The phase 0 registry is loaded from Appendix A, so it must be complete for phase 1.
  - Missing settings:
    - the authority preset and its six verbs;
    - the project timezone and the person timezone (`brief.time` is "local");
    - the Operate cycle period, roll day and due time;
    - the personal token default expiry.
  - GOV-1 is written for project settings, but the registry also has person and install scopes. Requiring a 10-character reason for `/brevity` makes no sense.
  - There are no cross-setting constraints. For example, `budget.warn_at` 95% with `budget.wrapup_at` 60% is accepted.
  - NFR-7 operational settings (sandbox CPU and memory, ports) are environment variables, outside the registry. CLAUDE.md says every tunable number is in the registry.
- **Recommendation:**
  - Add the missing settings:
    - `authority.preset` [autonomous]: autonomous or supervised;
    - `authority.accept_scope`, `authority.change_scope`, `authority.date`, `authority.verdict`, `authority.credential_rescope` and `authority.reserve_draw`: each ceo, reviewer or chairman, within the limits of section 3;
    - `project.timezone` [the creator's timezone] and `person.timezone`;
    - `cycle.period` (hourly to quarterly), `cycle.roll_day` and `cycle.due_time`, for Operate;
    - `token.default_expiry` [30 days], range 1–365, scope person.
  - Scope GOV-1:
    - reason, versioning and CEO disclosure apply to project settings;
    - person settings are preferences changed by that person, audited without a reason;
    - install settings are changed by an admin with a reason.
  - Add a "Constraints" list to Appendix A (first entry: `budget.warn_at` < `budget.wrapup_at`), validated as a bundle per GOV-1.
  - State in Appendix A that operational settings (NFR-7) are listed in their own table, with their defaults. That table is the registry for numbers that are environment-configured.

### R-11 Phase 1 ids that depend on later phases

- **Ref:** PLAN phase 1; PRJ-9; IF-4.6; IF-4.7; NFR-2; NFR-5; PRJ-1; PRJ-2; PRJ-3; PRJ-10; IF-5.1; IF-5.2.
- **Quote:**
  - PRJ-9: "Export produces a spec (LIB-4)". LIB-4 is in phase 7.
  - IF-4.6: "Drafting a project in the terminal follows the Founder rules (FND-3)". The Founder is in phase 7.
  - NFR-2: "loads the starter libraries; offers guided Slack and email setup". Libraries are in phase 7; Slack and email in phase 8.
  - PLAN phase 1 exit: "See every change in the event log from … an MCP client", but MCP auth (IF-5.1) and scopes (IF-5.2) are in phase 6.
- **Problem:** Phase 1 cannot close these ids honestly. The exit demo needs MCP authentication that the plan schedules five phases later.
- **Recommendation:**
  - Move PRJ-9 (clone and export) to phase 7, beside LIB-4.
  - Move IF-4.6 and IF-4.7 to phase 7.
  - Keep NFR-2 and NFR-5 in phase 1 for the parts that exist; the Slack, email and library steps are added in their phases and noted in the matrix.
  - Keep PRJ-1, PRJ-2, PRJ-3 and PRJ-10 in phase 1, with a start-check and stop-hook registry, so later phases add their checks without changing project code. Record this in the matrix notes.
  - Pull into phase 1 the minted-bearer-token part of IF-5.1 and the `read` scope of IF-5.2. OAuth stays in phase 6.

---

## 1. Contradictions (non-blocking)

### R-20 Reaping releases claims, but the claim survives retries (before phase 2)
- **Ref:** EXE-7, EXE-8, WRK-4, INV-16.
- **Quote:** EXE-7: "Reaping … releases claims, except a lead's task with open subtasks." WRK-4: "A claim with no live run behind it for 2 × `run.timeout` returns the task to ready." EXE-8: retried up to 3 attempts.
- **Problem:** If reaping releases the claim, the retry has no task. If it does not, EXE-7 is wrong.
- **Recommendation:** Reaping keeps the claim while a retry is scheduled. The claim returns to ready when retries are exhausted, or after 2 × `run.timeout` with no live run.

### R-21 Context pack order: what comes "first" (before phase 2)
- **Ref:** CHAT-11, MSG-10, EXE-15.
- **Quote:** CHAT-11: "The chairman's newest unanswered message is always first in the agent's context". EXE-15 puts pinned memory first.
- **Recommendation:** Reword CHAT-11 to "first among the messages in the agent's context, directly after pinned memory".

### R-22 Sandbox network: "cannot reach the control plane" versus the agent API inside the sandbox (before phase 2)
- **Ref:** EXE-14, EXE-17, IF-6, LLM-8, EXE-12.
- **Quote:** EXE-14: "Egress is open by default, with no proxy". EXE-17: "The browser cannot reach private addresses, the control plane or another project's network".
- **Problem:**
  - The harness must reach the gateway and the agent API from the sandbox.
  - If egress is open, `curl` from the shell can reach the private addresses the browser is denied, so the browser restriction contains nothing.
- **Recommendation:**
  - Enforce at the network level for the whole sandbox: private, link-local and metadata ranges are blocked, except the gateway and agent API endpoints.
  - Make the browser rule a consequence of that, not a separate rule.
  - Check sandboxes (WRK-7) get no network unless the operator allows it.
  - State all of this in SECURITY.md.

### R-23 Directive applying a setting versus INV-1 (before phase 3)
- **Ref:** MSG-3, INV-1, P7.
- **Quote:** MSG-3: "`/do set quality to best` applies the setting as the chairman's own change". INV-1: "No agent action writes … a setting".
- **Recommendation:** Directives that touch P7-reserved values are parsed by the platform into an operation that the chairman confirms on an action card. The operation is executed with the chairman as actor. The agent never calls the setting operation.

### R-24 Wrap-up mode leaves Explore with no tasks (before phase 5)
- **Ref:** GOV-3, GOV-10, PRJ-7.
- **Quote:** GOV-3: "New tasks are refused unless they serve a requirement already in progress." Explore tasks serve bets.
- **Problem:** At 90%, an Explore project cannot create any task, even to finish an active bet, yet GOV-10 lets the reserve fund findings for active bets.
- **Recommendation:** "…unless they serve a requirement already in progress or a bet already active."

### R-25 Plan and section 13 build order disagree (before phase 2)
- **Ref:** PLAN.md; ADR-0007; section 13 build order; ACC-7; section 14.
- **Problem:**
  - **Lineup overrides and circuit breakers:** PLAN puts LLM-4 and LLM-11 in phase 2; section 13 says phase 8.
  - **MCP configure scope and OAuth:** PLAN puts them in phase 6 (IF-5.1, IF-5.2, NFR-13); section 13 says phase 8.
  - **Agent Skills:** section 13 puts them in phase 7; PLAN and ADR-0007 say phase 8.
  - **TOTP:** ACC-7 says "SHOULD for v2.0"; section 14 recommends v2.0; PLAN puts ACC-7 in phase 8.
  - **Providers and harnesses:** section 13's acceptance "Multi-provider" (three providers plus a subscription credential) is in the v2.0 suite, while PLAN puts "more providers and harnesses" in phase 8.
- **Recommendation:** PLAN and ADR-0007 are the newer owner decisions. Rewrite the section 13 build order to match PLAN. Mark ACC-7 as after v2.0. Mark the Multi-provider acceptance item as deferred, like Standards, or keep three providers in v2.0 through LiteLLM's registry entries, which cost little (owner's choice).

### R-26 MEM-1 says Postgres only (before phase 3)
- **Ref:** MEM-1, NFR-8, NFR-23.
- **Quote:** "Stored as governed records in Postgres".
- **Recommendation:** "Stored as governed records in the project database."

### R-27 HUM-3 "only … conclude positively" versus other defaults (before phase 6)
- **Ref:** HUM-2, HUM-3, P6.
- **Quote:** HUM-3: "Only delivery sign-off and green status reviews conclude positively by default". HUM-2: a question's default is "The CEO's stated default stands".
- **Problem:** A question's stated default is an action. P6 forbids defaults that spend, grant, widen scope or cut chairman scope, but nothing constrains what the CEO states as the default.
- **Recommendation:** A question's default must be an action within the CEO's current authority, and may not spend, grant or widen scope. The default is validated with the `concerns` field (HUM-4).

### R-28 Pinned-memory caps versus chairman writes (before phase 3)
- **Ref:** MEM-1, MSG-4, MSG-6, HUM-8, INV-25.
- **Quote:** "A write past a cap is refused, naming what to retire."
- **Problem:**
  - A chairman's `/fix` or `/pin`, or a filed mistake report's lesson, can be refused by a cap. That makes the chairman fight a refusal, and a filed report cannot be edited.
  - 25 standing orders of 400 characters plus a 6,000-character goal can exceed the 2,000-token minimum of `memory.pinned_project_tokens`.
- **Recommendation:**
  - Chairman writes are never refused. They succeed and open a flag asking the chairman to retire records.
  - Agent writes (pinned notes) are refused at the cap.
  - Lowering the cap below current use is refused, with the arithmetic.

### R-29 NFR-20 warn-only rules versus P1 and invariant wording (before phase 1, non-blocking)
- **Ref:** NFR-20, P1, EXE-10.
- **Quote:** "New rules ship in warn-only mode first, unless they guard authority, budget, secrets or side effects."
- **Problem:** The spec never lists which v2.0 rules start warn-only. Candidates are the WRK-3 Explore floors, MSG-9 and HUM-4.
- **Recommendation:** The rule registry carries `mode` (enforce or warn) from phase 1. Every rule cited by an invariant is enforce-only. Each phase plan lists its warn-only rules.

### R-30 Email thread freeze uses two settings (before phase 8)
- **Ref:** INT-6 `email.thread_freeze_after` [40]; INT-10 `thread.freeze_after` [10].
- **Recommendation:** State plainly: the INT-10 loop guard (10 consecutive agent-to-external messages with no state change) is MSG-9, and `email.thread_freeze_after` caps any thread's total length. Or merge them.

### R-31 Founder tokens "not billed to any project" versus INV-8 (before phase 7)
- **Ref:** FND-2, P9, INV-8.
- **Recommendation:** Founder calls get ledger lines against an install-level account. They are metered, but count against no project budget.

### R-32 Quick mode timing: three numbers (before phase 7)
- **Ref:** FND-12 "about a minute"; section 1.3 "2 minutes"; section 13 "under 2 minutes".
- **Recommendation:** Use one target, under 2 minutes, and cite section 1.3.

### R-33 IF-5.6 human-only list versus the parity matrix (before phase 6)
- **Ref:** IF-5.6, 9.8, IF-5.2.
- **Problem:**
  - The matrix marks skill approval as human-only, but IF-5.6 does not list it.
  - The matrix gives MCP steer "reopen, complete" and "edit memory", but the IF-5.2 steer list lacks them.
- **Recommendation:** Make IF-5.6 and IF-5.2 the sources, and add the missing verbs there.

## 2. Ambiguous or untestable (non-blocking)

### R-34 Hold reason (before phase 1)
- **Ref:** PRJ-2 "recorded with a reason"; CHAT-5 `/hold [until <time>]`.
- **Recommendation:** The reason is optional free text, with the default "held by the chairman". The 10-character rule applies only to settings.

### R-35 What a chat run is (before phase 2)
- **Ref:** MSG-11, 7.7, EXE-7, INV-13.
- **Problem:** A warm session lasts `chat.keep_warm` after the last message. The spec does not say whether that is one run or one run per message, nor how heartbeat, `run.timeout` and the per-run cap apply.
- **Recommendation:** One chat *session* holds many chat *runs*, one per reply. Each run is metered and capped separately. The session is not a run and is not reaped.

### R-36 Run retry identity (before phase 2)
- **Ref:** EXE-8, 7.7.
- **Recommendation:** Each attempt is a new run linked to the same wake. `failed` stays terminal, and the wake counts once.

### R-37 INV-13 when concurrency is lowered (before phase 2)
- **Ref:** INV-13, GOV-7 (spinning drops concurrency to 1).
- **Problem:** "never exceeds" is broken the instant the limit drops below the number of running runs.
- **Recommendation:** "Nothing new is leased while the count is at or above `run.concurrency`."

### R-38 Locked artifacts in a read-write workspace (before phase 2)
- **Ref:** ART-5, EXE-12.
- **Quote:** "Agent writes to a locked artifact are refused".
- **Problem:** The workspace is mounted read-write, so a shell write cannot be refused at call time.
- **Recommendation:** Locked files are mounted read-only into the sandbox, the same way pinned test files are restored for checks. A write attempt is recorded as a refusal.

### R-39 Storage quota at 100% (before phase 2)
- **Ref:** ART-6.
- **Recommendation:** At the quota, publishing new versions is refused and the workspace snapshot is skipped, with a flag.

### R-40 "Work has changed since the last ruling" (before phase 5)
- **Ref:** PLN-10.
- **Recommendation:** A task under the requirement reached done after the last ruling, or the workspace snapshot hash changed.

### R-41 "The same command test" (before phase 4)
- **Ref:** WRK-3 "the check is the suspect".
- **Recommendation:** The same pinned command string and the same `test_files` hashes.

### R-42 "and similar" in can't-fail commands (before phase 4)
- **Ref:** WRK-5.
- **Recommendation:** Use a fixed denylist. The red-first run already catches every other command that always passes. Drop "and similar".

### R-43 Evidence "postdates the task" (before phase 4)
- **Ref:** WRK-12.
- **Problem:** Most web pages carry no reliable event time.
- **Recommendation:** Required: the fetch happened after the task was created, and the claimed content was found on the page. Event-time comparison applies only where the source supplies a timestamp (webhooks, APIs).

### R-44 Metric requirements reaching met (before phase 5)
- **Ref:** PLN-10, PLN-11, section 4 "Metric".
- **Problem:** PLN-10 covers only command and observable tests.
- **Recommendation:** A metric requirement is met when a platform reading reaches its target. Recurring metric requirements reset at the cycle roll.

### R-45 Skipped versus missed cycle (before phase 5)
- **Ref:** PRJ-8, PRJ table.
- **Recommendation:**
  - **Skipped:** no work run happened in the cycle because the project was held or paused.
  - **Missed:** work ran but recurring scope stayed open at the due time.

  Also define weekday numbering for `cycle.roll_day`: 0 = Monday, as in ISO.

### R-46 Explore reserve "funds only findings" (before phase 5)
- **Ref:** GOV-10.
- **Recommendation:** After an Explore draw, only tasks serving active bets may be created, and no bets may be opened. Make the Deliver rule explicit: when plan tokens are "unknown" (PLN-3), the draw is refused.

### R-47 State flags versus event flags (before phase 6)
- **Ref:** HUM-6.
- **Recommendation:** Mark each flag kind in the HUM-6 table as **state** (clears with its condition) or **event** (closes by raise and acknowledge).

### R-48 INV-22 "next wake" (before phase 6)
- **Ref:** INV-22, HUM-12.
- **Problem:** Message-driven wakes cannot be predicted.
- **Recommendation:** Compare only the next *time-based* wake: heartbeat, not-before, deadlines, cycle roll, watch.

### R-49 Who writes the proposed standing order and decision text (before phase 3)
- **Ref:** MSG-4 "The platform proposes a one-sentence order", MSG-5.
- **Problem:** Condensing a message to one sentence needs a model.
- **Recommendation:** A platform model call on the fast class, metered to the project and labelled. Alternatively, the chairman's own sentence with no model call.

### R-50 MSG-7 "a reviewer check flags any figure" (before phase 3)
- **Recommendation:** A mechanical platform lint, not a reviewer seat.

### R-51 Rehearsal "refuses to run against a real database" (before phase 7)
- **Ref:** RHS-1.
- **Recommendation:** Rehearsal always runs on a fresh in-memory SQLite, and the code path refuses any other URL.

### R-52 Slim mode memory target with a local embedding model (before phase 3)
- **Ref:** NFR-23 (idle under 400 MB, start under 5 s), MEM-2.
- **Problem:** A PyTorch-based embedding model alone typically exceeds both targets. Separately, MEM-2 requires keyword-plus-vector hybrid retrieval. Whether Mem0 supplies BM25 on both stores needs checking.
- **Recommendation:**
  - Use an ONNX-based embedder, loaded lazily on first use.
  - Measure in the phase 3 plan.
  - Settle hybrid retrieval with Q-001.

## 3. State transitions (non-blocking)

### R-53 Task: platform transitions missing from 7.3 (before phase 4)
- **Problem:**
  - **Bet expiry:** PRJ-7 says "open tasks block", including ready tasks, but 7.3 has only `claimed → blocked` by the claimant.
  - **Requirement cut:** a cut requirement leaves its open tasks with no transition. They need `ready, claimed, blocked → killed` by the platform.
- **Recommendation:** Add rows for platform `ready, claimed → blocked` (bet expired) and platform `ready, claimed, blocked → killed` (requirement cut).

### R-54 Task returning to the claimant after the claimant moved on (before phase 4)
- **Ref:** 7.3 `checking, review → claimed`; WRK-4 "An agent holds one item at a time".
- **Recommendation:** A failed check returns the task to `ready`, reserved for the previous claimant, and the failure count carries over. The claimant takes it back when free.

### R-55 INV-18 wording (before phase 5)
- **Quote:** "no task exists under a requirement that is not ready for work".
- **Problem:** A met requirement has done tasks under it, which breaks the invariant as written.
- **Recommendation:** "No task is *created* under a requirement that is not ready for work, and no open task remains under a cut one."

### R-56 Solo `claimed → done` (before phase 4)
- **Recommendation:** Restrict the row to observable tests (INV-2). See R-01.

### R-57 Requirement and commitment: platform default transitions (before phase 5)
- **Ref:** HUM-2 (proposed scope and proposed commitment default to "Not accepted" at 72 h); 7.2; 7.6.
- **Recommendation:** Add `proposed → declined` by the platform at the deadline, with the reason "not accepted in time". Add the recurring `met → accepted` (cycle roll) as a proper row.

### R-58 Commitment: chairman moves the date (before phase 5)
- **Ref:** PLN-6, PLN-8, HUM-9 ("move the date").
- **Recommendation:** Add a row `accepted, at risk, breached → accepted` with a new chairman date, Who: Chairman.

### R-59 Run: leased but never started (before phase 2)
- **Recommendation:** Add `leased → reaped` (lease TTL expired before the sandbox started) and `leased → killed` (revoked).

### R-60 Decision items: states beyond 7.5 (before phase 6)
- **Problem:** The table lacks:
  - flags: raised, acknowledged, cleared;
  - heads-up: archived;
  - mistake report: owed, filed (by the CEO);
  - audit sample: expired;
  - status review: auto-closed.
- **Recommendation:** Extend 7.5 with these and their actors.

### R-61 Ready project, CEO adding scope (before phase 5)
- **Ref:** 7.1 `ready → running` "CEO with plan or scope authority"; PRJ-5; INV-20.
- **Problem:** In a ready project the CEO gets only chat runs, which change state only through a directive.
- **Recommendation:** Keep the row, and note that it is reached only through a chairman directive.

### R-62 Operate never ends except by stop (before phase 5)
- **Ref:** PRJ table: "Never by itself"; 7.1.
- **Recommendation:** Add `running, held, paused → completed` for Operate by the chairman, with a final scorecard, so a finished operation does not have to be "stopped" and lose its pending items as denials.

## 4. Settings (non-blocking)

### R-63 "Used by" column drift
- **Problem:** The registry's "Used by" column misses some cites:
  - `budget.tokens`: GOV-3, GOV-10;
  - `budget.wrapup_at`: GOV-10, HUM-6;
  - `run.max_tokens`: INV-9;
  - `run.concurrency`: INV-13, PLN-5;
  - `delete.grace`: INT-6;
  - `upload.max_size`: IF-3.9;
  - `spend.monthly_cap`: INV-10;
  - `spend.approval_at`: GOV-10.

  `budget.ceo_reserve` lists GOV-3, which does not cite it. `question.window` lists HUM-5, `chat.brevity` lists MSG-12 and `grill.pace` lists FND-15 and FND-16, but none of those cites the setting.
- **Recommendation:** Generate the column from the spec in CI (a small check script), or fix it by hand.

### R-64 Fixed numbers that read as tunable
- **Problem:** Several fixed numbers behave like settings:
  - ACC-3 token life has a default and a range;
  - HUM-2 "Approval: legal | 7 days" while its sibling uses `approval.window`;
  - MSG-10's 10 unread messages per channel;
  - IF-5.7 context budgets.
- **Recommendation:** ACC-3 becomes a setting (R-10). Legal and tool-permission approvals use `approval.window`. The rest are fixed rules, as section 0 allows.

### R-65 Conditional range for `review.independent`
- **Quote:** "on; off only when solo".
- **Recommendation:** Express it as a cross-setting constraint against the org shape, in the constraints list proposed in R-10.

### R-66 `report.cadence` slots
- **Problem:** "1–4 slots a day" names no times.
- **Recommendation:** Slots are evenly spaced from `brief.time`, or the setting takes explicit times (before phase 3).

## 5. Phase dependencies (non-blocking)

Phases 0–7 referencing phase 8 work, or a later phase. Phase 1 items are covered by R-11.

### R-67 Roles before the role library
- **Ref:** EXE-1, EXE-13, LLM-6 (phase 2) need roles; LIB-1 is phase 7.
- **Recommendation:** Phase 2 ships a minimal role model (name, kind, tools, credential names, charter) that LIB-1 extends.

### R-68 LIB-6 referenced from phase 2 and 7
- **Ref:** LLM-8 ("load skills natively … LIB-6"), IF-6.3 ("loading granted skills (LIB-6)"), LIB-1 ("the skills it may use").
- **Recommendation:** These fields exist but are empty until phase 8. Note it in the matrix.

### R-69 INV-10 and INV-14 in phase 2
- **Ref:** INV-10 needs GOV-8 (phase 6); INV-14 needs WRK-16 (phase 4).
- **Recommendation:** Move INV-10 to phase 6 and INV-14 to phase 4.

### R-70 CHAT-1, CHAT-5, CHAT-18 and CHAT-20 in phase 2
- **Problem:** They reference the Founder (phase 7), `/pin` and related commands (phase 3), `/desk` and the agenda (phase 6), and Slack (phase 8).
- **Recommendation:** Accept partial delivery, with each missing piece noted in the matrix.

### R-71 GOV-3 in phase 2
- **Problem:** It references the reserve (phase 5), the budget decision item (phase 6) and alarms (phase 6).
- **Recommendation:** Phase 2 delivers the wall and the pause. The rest follows in later phases and is noted.

### R-72 EXE-2 wake triggers
- **Problem:** Some triggers (mail, watch, flags) belong to later phases.
- **Recommendation:** Build the trigger registry in phase 2 and add triggers per phase.

### R-73 WRK-17 browser-script watches
- **Problem:** Phase 4 references EXE-17, which is phase 8.
- **Recommendation:** Phase 4 ships the command and URL watches only.

### R-74 IF-1.3 decision-item kinds on Slack
- **Problem:** IF-1.3 requires each kind on every HUM-1 surface, Slack included, and Slack is phase 8.
- **Recommendation:** Use a surface-wide exemption until phase 8 (R-06).

## Housekeeping

- Section 14's open questions are mostly settled by ADRs 0001 to 0007 (rebuild, Python, databases, token budgets, Mem0). Move the decided ones to a "Decided" list with their ADR. Keep egress, workspace snapshots and default skill sources as open questions.
- INV-21's actor kinds omit the Founder (7.1 "Founder in quick mode") and admin break-glass (section 3). Add both.
