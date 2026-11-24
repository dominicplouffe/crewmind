# Phase 4 plan: verification

Goal (PLAN.md): "done" means checked by something other than the doer.

**Exit demo.**

- The rule-breaker acceptance scenario passes: a scripted agent tries every forbidden action that exists so far in INV-1 to INV-7 and INV-23, is refused each time, hits the refusal cap and has its token revoked. No forbidden state is reached.
- A test that passes before any work is refused.
- A launch without a watch is refused.

Status: **agreed with the owner on 22 Nov 2026.** The answers are at the end.

## What phase 4 covers

23 requirement ids: WRK-1 to WRK-10 and WRK-12 to WRK-17; INV-1, INV-2, INV-3, INV-14, INV-16; EXE-16 and the spinning guard of GOV-7 (both moved here from phase 2).

This is the first phase with tasks. Until now the CEO only talked, hired and published. From here it creates tasks, teams claim them, and nothing is done until the platform or another agent has checked it.

## Four parts

Each part ends with the suite green on both databases.

| Part | Builds | Demo |
| --- | --- | --- |
| **4a Tasks** | Task content, who creates, ceilings and floors, claim and claim expiry, subtasks, suggestions, block and kill (WRK-1 to WRK-4, WRK-14, INV-16), the task lifecycle of section 7.3, the stall watchdog (EXE-16) and the spinning guard (GOV-7) | The CEO creates a task, a lead claims it and splits it; a claim with no live run returns to ready; an idle project with open work alarms once |
| **4b Checks** | Tests must fail first, pinned commands and test files, platform checks in a fresh sandbox with no model and no credentials, the failure loop (WRK-5 to WRK-8, INV-2) | A test that already passes is refused; a task reaches done only when the platform's own run of the pinned command exits 0; editing the test file does not help |
| **4c Reviews and labels** | Independent read by a reviewer seat, reviewer staffing rules, sampled audit, honest labels, the basis of figures in deliverables (WRK-9, WRK-10 part, WRK-13, WRK-15, INV-3) | An author cannot review its own work; a solo project's close is labelled "self-reported"; one in five observable closes is drawn for the chairman |
| **4d The outside world** | Outside evidence with its verifier and SSRF guard, side effects with idempotency keys, launches and watches (WRK-12, WRK-16, WRK-17, INV-14) | A side effect fires once across retries; a launch without a watch is refused; a failing watch wakes the seat that launched it |

The web app gets a Board panel in part 4c: tasks by state with their honest labels, reviews waiting, audit samples for the chairman, and launches with their watches.

## What does not exist yet, and what stands in for it

Phase 4's requirements lean on three domains that come later. The plan uses the smallest honest stand-in for each and says so in the product.

| Later domain | Needed by | Stand-in in phase 4 |
| --- | --- | --- |
| **Requirements and bets** (PLN, phase 5) | "The requirement or bet it serves" (WRK-1); "evidence must name a real task" works already | A task may name what it serves in words. The link to a requirement becomes required in phase 5. Explore's bet rules (expiry blocks tasks) arrive with bets |
| **Flags, the desk, decision items, mistake reports** (HUM, phase 6) | Watch-failing flag, "the CEO is told", "the chairman gets an alarm", the audit sample the chairman passes or fails, "a mistake report is owed" | Chat status lines, notices to agents and push alarms, as phases 2 and 3 already do. Audit samples get their own list and operations. The decision-item half of WRK-10 and the mistake report of WRK-13 arrive in phase 6 |
| **Deliver readiness and the goal's named standard** (PRJ-4, FND-7; phases 5 and 7) | Final gap review (WRK-11) | Moved to phase 5 by the owner |

## Modules

```
src/nightsquad/
  domain/work/
    model.py           task states (7.3), evidence (7.15), side effect and watch (7.16)
    tasks.py           create, ceilings and floors, claim, expiry, complete, block, kill
    suggestions.py     suggestions to the CEO, given back if its planning run fails
    checks.py          red-first, pinning, the can't-fail list, running a pinned check
    reviews.py         independent read, reviewer staffing, closed unread
    audit.py           sampled audit of observable closes
    labels.py          verified, reviewed, self-reported, not yet checked (WRK-15)
    evidence.py        outside evidence and its verifier
    fetch.py           the SSRF guard: public addresses only, redirects re-checked
    effects.py         side effects, launches and watches
    operations.py      tasks.*, reviews.*, audits.*, evidence.*, launches.* for people
    agent_operations.py  agent.create_task, claim, complete, review, block, kill,
                         suggest, file_evidence, declare_effect, finish_effect, ...
  runner/
    check_sandbox.py   a sandbox for a check: no model, no token, 1 CPU, 1 GB, a timeout
  jobs/
    work.py            claim expiry, checks due, evidence to verify, watches due,
                       audit expiry, the stall watchdog, the spinning guard
web/src/panels/board/  the Board panel
acceptance/scripts/    the rule-breaker and competent-squad scripts for the mock harness
```

The context pack gains "the board": the agent's claimed task with its attempt history, what it may claim, and for the CEO the open tasks and suggestions.

## Operations

| Operation | Who |
| --- | --- |
| `agent.create_task`, `agent.create_subtask` | CEO; a lead under a parent it has claimed |
| `agent.claim_task`, `agent.complete_task`, `agent.block_task`, `agent.kill_task` | The lead or assignee; the claimant; the CEO or lead |
| `agent.suggest` | Any agent; creates no work |
| `agent.review_task` | A reviewer seat other than the author |
| `agent.file_evidence`, `agent.declare_effect`, `agent.finish_effect`, `agent.retire_launch` | The agent doing the work |
| `tasks.list`, `tasks.show`, `reviews.list`, `evidence.list`, `launches.list` | People, observers included; MCP read |
| `audits.list`, `audits.pass`, `audits.fail` | The chairman |
| `launches.retire` | The chairman |

No operation lets a person create or complete a task: the chairman steers through directives (P15), and the CEO plans.

## Tables (migration 0011)

- `tasks`: project, parent, title, goal, success test and its kind (command or observable), test files and their hashes, outside-evidence flag, audience, what it serves, not-before, state, claimant, author, completion evidence, check output, failure count, label.
- `task_attempts`: the last 5 attempts of each task.
- `suggestions`: project, author, text, the planning run it was handed to.
- `reviews`: task, reviewer seat, verdict, notes.
- `audit_samples`: task, drawn or skipped, verdict, expiry.
- `evidence`: project, task, URL, state, snapshot hash, fetch attempts.
- `side_effects`: project, run, idempotency key, kind (effect or launch), state, what happened.
- `watches`: launch, kind, check, interval, state, last result.

Every lifecycle is already in section 7 (7.3, 7.15, 7.16) and is added to the drift test.

## Settings used

`tasks.max_open`, `tasks.max_subtasks`, `evidence.min_share`, `evidence.drought_after`, `review.independent`, `audit.sample_rate`, `audit.window`, `watch.min_interval`, `run.timeout`, `stall.after`, `spin.window`, `NIGHTSQUAD_ALLOW_AGENT_CHECKS_UNISOLATED`. All exist in the registry. The fixed numbers the spec states (3 failures, 5 attempts kept, 6 hours ahead, 15 and 10 characters, 300 seconds, 1 CPU and 1 GB, 5 fetch retries, 20 seconds, 2 MB) are constants citing their requirement.

## Tests to write first

1. **The task table (7.3)** as a table-driven test, plus a property test: no sequence of agent calls moves a command-test task to done without a platform check that exited 0 (INV-2).
2. **INV-3:** the author cannot complete for another, review its own work, or claim a task whose test it wrote while another active agent exists; a solo project is exempt for observable tests only, and labelled.
3. **INV-16, chaos:** kill a runner while its agent holds a claim; the task returns to ready after 2 × `run.timeout` and another agent finishes it.
4. **Red first:** a test that passes on the current workspace is refused; each can't-fail command is refused; after the claimant edits the test file, the check still runs the pinned version.
5. **INV-14, chaos:** a run retried three times declares the same side effect each time; it fires once.
6. **The SSRF guard:** private, loopback and link-local addresses, a redirect to one, an oversized body and a slow server are all refused, against a local test server.
7. **The rule-breaker scenario:** one scripted agent attempts each forbidden action that exists, across INV-1 to INV-7 and INV-23; every attempt is refused, the refusal cap ends the run and the token is revoked.
8. **Attack tests** for each new rule, as before.

Tests follow the rules in CLAUDE.md: independent, parallel, no real waiting. Checks in tests run trivial shell commands in a temporary workspace.

## What I can and cannot verify here

- **Checks run as plain processes in this environment.** There is still no Docker daemon, so the container sandbox for checks is written but not run, like the agent sandbox. The process version has a clean environment, a timeout and resource limits.
- **The evidence verifier is tested against a local server.** A fetch of a real public page is not part of the suite.
- **No real model is called,** as agreed.

## Review items I plan to apply

These were marked "before phase 4" in `docs/spec-review.md` (question 3).

| Item | Change |
| --- | --- |
| R-41 | "The same command test" means the same pinned command string and the same test-file hashes |
| R-42 | Can't-fail commands are a fixed list; "and similar" is dropped, because the red-first run catches the rest |
| R-43 | Evidence "postdates the task" means the fetch happened after the task was created and the claimed content was found on the page; event times are compared only where the source supplies one |
| R-54 | A failed check or rejected review returns the task to ready, reserved for its previous claimant, so an agent that has moved on is not forced to hold two items |

R-53 and R-56 are already in the section 7.3 table.

## Rules that start in warn-only mode (NFR-20)

None. The new rules guard verification, authority and side effects, and INV-2, INV-3, INV-14 and INV-16 are invariants.

## Risks

- **Refusal loops.** Tasks bring many new refusals (ceilings, red-first, one item at a time). Each refusal says what to do instead, the refusal cap ends a run that keeps hitting them, and the scenario suite includes a competent squad that must finish a small job without tripping them.
- **Scripted squads are harder to write than scripted chats.** The mock harness may need a small helper so a script can refer to "the task I just created".
- **The spinning guard needs a definition of "changed work state".** I will use: a task changed state, or an artifact version was published.

## Owner answers (22 Nov 2026)

| Question | Answer |
| --- | --- |
| Review stops | **One stop, at the full exit demo** |
| The final gap review (WRK-11) | **Moved to phase 5,** with its exit-demo line, where requirements and Deliver readiness are built |
| Review items R-41, R-42, R-43, R-54 | Accepted as recommended; applied in spec revision 2.11 |
| The Board panel | **Built in this phase** |

No open questions remain.

## Outcome (22 Nov 2026)

Phase 4 is built in its four parts. Of its 23 requirement ids, 16 are done, 6 are partial and 1 is not started; `docs/traceability.csv` has the tests and a note for each.

**Exit demo, item by item.**

| Item | Result |
| --- | --- |
| The rule-breaker scenario | Passes. A scripted agent tries to complete a task it does not hold, review it, kill it, overwrite a locked file, re-argue a closed decision, create its own task and write a standing order. Each call is refused, the fifth refusal ends the run and revokes its token, and nothing it wanted is reached. With a run token it also cannot do anything only the chairman may |
| A test that passes before any work is refused | Passes, with the can't-fail list and missing test files |
| A launch without a watch is refused | Passes |
| (Added) A competent squad finishes a verified job | Passes in-process with no refusals, and as real processes: separate agent processes do the work and the server's own check closes it as verified |

**What "done" means now.**

- A task with a command test is done only when the platform's run of the pinned command exits 0. Rewriting the test file does not help: the check restores the pinned version in a copy of the workspace.
- A task with an observable test is judged by a reviewer seat that neither did the work nor wrote the test.
- A solo project with independent read off closes as "self-reported", and says so everywhere.
- One in five observable closes (`audit.sample_rate`) is drawn for the chairman.

**Partial or not built.**

- **WRK-10 (figures need a basis):** not built. Decision items arrive in phase 6; asked to move it there (Q-010).
- **WRK-7:** checks run as processes with a clean environment, a memory limit and a timeout. The container version (no network, 1 CPU, 1 GB) was proven on 22 Nov 2026 (`test_WRK_7_a_check_container`).
- **WRK-12:** the verifier and its network guard are tested against a local server only. Signed webhook evidence arrives with integrations.
- **WRK-13:** the mistake report a failed audit owes arrives in phase 6.
- **WRK-17:** browser-script watches arrive with the agent browser. The watch-failing flag is a chat line and a push alarm until flags exist.
- **WRK-1:** "the requirement it serves" is free text until phase 5.
- **INV-1:** covered for what exists (settings, orders, decisions, corrections, verdicts on own work, locked files). Commitments, tool permissions, revenue lines and flags arrive later.
- **Web:** the Evidence tab was only seen empty; subtask nesting, and several states and labels (checking, killed, closed unread, verified, self-reported), are unit-tested but were not driven in a browser. Alarm lines in the chat have no special style.

**Things to know.**

- **Every project now starts with a second agent, a Reviewer,** staffed by the platform because independent read is on by default. **Solo works from start to finish** (owner, Q-009): the CEO creates, claims and does its own tasks, and the check or the reviewer closes them. With independent read off a solo project is one agent: the reviewer is stood down, work closes as self-reported, and the reviewer comes back when independent read is turned on again. A scripted scenario covers all of it.
- **A side effect can get stuck.** If the declaring run and all its retries die after declaring it, nothing can finish it and the chairman cannot retire it. Built to the letter of the spec; a fix is proposed in Q-011.
- **With the mock provider, a solo CEO that creates a task is woken again to claim it** and replays its script. A real model would simply claim the task.

**Found and fixed on the way.**

- Words of a reply stopped with Esc could arrive late and bring the typing bubble back. This was the flaky browser test from phase 2.
- Test database cleanup on Postgres could fail when a server background worker was in the database.

**Tests.** 344 Python tests on SQLite in about 110 seconds and 345 on Postgres in about 150 seconds; 95 web unit tests; 41 browser tests in about 2.6 minutes.

**Open questions for the owner:** Q-010 (move WRK-10 to phase 6) and Q-011 (side effects that can never be finished). Q-009 is closed.
