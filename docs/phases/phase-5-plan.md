# Phase 5 plan: planning and speed

Goal (PLAN.md): the three project types, honest projections, and speed as a requirement.

**Exit demo.**

- The golden path passes for all three types: a Deliver project ships and completes, an Explore project confirms one bet and kills another, and an Operate project meets a recurring requirement across cycles.
- The speed acceptance criterion passes: the Deliver reference project with concurrency 4 completes in no more than 1.3 × (its longest dependency chain × the median scripted run duration), and no ready task waits more than 10 seconds for a lease when limits allow.
- A nearly finished Deliver project draws the CEO reserve, and a half-finished one is refused.

Status: **agreed with the owner on 22 Nov 2026.** The answers are at the end.

## What phase 5 covers

32 requirement ids, the largest phase so far: PRJ-4 to PRJ-8; SPD-1 to SPD-4 and SPD-6 to SPD-9; GOV-4, GOV-5, GOV-10; PLN-1 to PLN-12; INV-18, INV-19; and WRK-11, moved here from phase 4.

Until now a task named what it serves in words. From this phase, scope is real: a task in a Deliver or Operate project must serve an accepted, estimated requirement that is ready for work, and a task in an Explore project must serve an active bet (INV-18).

## Five parts

Each part ends with the suite green on both databases.

| Part | Builds | Demo |
| --- | --- | --- |
| **5a Requirements** | Requirements and their lifecycle (7.2), who may accept and change scope, dependencies and stages, "ready for work", fitting the budget, requirement acceptance by check or verdict, stand-down conditions (PLN-1, PLN-2, PLN-3, PLN-10, PLN-12, INV-18, INV-19) | A proposed requirement has no work; a dependency loop is refused and named; a requirement that does not fit the budget is refused with the arithmetic; only the platform writes "met" |
| **5b Dates and Deliver** | Throughput and projection, commitments with no date field, continuous re-projection, scope freeze, target dates, burn rate, raise requests, the CEO reserve, ready and complete with a receipt, reopen, the final gap review (PLN-4 to PLN-9, GOV-4, GOV-5, GOV-10, PRJ-4, PRJ-5, PRJ-6, WRK-11) | The Deliver golden path; the reserve drawn when nearly done and refused when half done; a commitment that turns at risk freezes new scope |
| **5c Explore** | Bets with kill conditions and dates, the time box, findings and the findings report, expiry and one extension (PRJ-7, SPD-7, 7.4) | The Explore golden path: one bet confirmed with verified evidence, one killed; no new bet in the last fifth of the time box |
| **5d Operate** | Cycles, recurring requirements, the roll with its scorecard, missed and skipped cycles, the pause after two skipped, metric requirements and "losing ground" (PRJ-8, PLN-11, 7.13) | The Operate golden path over three cycles; a paused project resumes into exactly one new cycle |
| **5e Speed** | Start at once, parallel by default with the longest chain shown, where the time went, and the slow-start, no-visible-output and idle-seat flags (SPD-1 to SPD-4, SPD-6, SPD-8, SPD-9) | The speed acceptance criterion, measured with real time on a scripted crew |

The web app gets a **Plan panel** with part 5b and grows with 5c to 5e: requirements with their dependencies and the longest chain, the projection and commitment, bets, the cycle scorecard, and where the time went.

## What does not exist yet, and what stands in for it

| Later domain | Needed by | Stand-in in phase 5 |
| --- | --- | --- |
| **Flags, the desk and decision items** (HUM, phase 6) | Slow start, no visible output, seat idle and losing ground flags; "the chairman gets an action item"; a proposal that is declined when nobody answers in 72 hours | Chat status lines, notices and push alarms, as before. The chairman accepts or declines scope, commitments and reserve draws with operations and buttons. The 72-hour default arrives with decision items |
| **The Founder** (phase 7) | Proposing a budget range, staffing enough seats, drafting the "first usable version" requirement, promoting an Explore project to Deliver | The burn rate and projected spend are shown (GOV-4, second half). The CEO writes the first requirement. Promote creates a draft Deliver project whose goal is the findings report; the Founder refines it later |
| **Data sources** (INT, phase 8) | Metric requirements read "from sources outside the project" (PLN-11) | A metric names a public URL and a pattern for the number; the platform fetches it through the fetch guard |
| **Questions to the chairman** (HUM-5, phase 6) | SPD-5: a question never blocks; rework is recorded against it | SPD-5 moves to phase 6 |
| **The spec format for a project** (LIB-4, phase 7) | The reference Deliver project the speed criterion runs | A scripted crew in `acceptance/scripts/`, like phase 4's |

## Modules

```
src/crewmind/
  domain/planning/
    model.py           requirement (7.2), bet (7.4), commitment (7.6), cycle (7.13) states
    requirements.py    propose, add, accept, decline, cut, reword, estimate, stage, reopen
    graph.py           the dependency graph: acyclic, longest chain, lowest open stage
    readiness.py       "ready for work" (PLN-2) and the check tasks.py asks before creation
    estimates.py       bias multiplier, median tokens per run, plan tokens, fits the budget
    acceptance.py      requirement checking, met by check or verdict (PLN-10)
    projection.py      throughput, projection, burn rate, projected spend (pure functions)
    commitments.py     propose, accept, decline, re-project, reset, scope freeze, target dates
    reserve.py         the CEO reserve: eligibility arithmetic, draw, cancel (GOV-10)
    raises.py          budget and concurrency raise requests (GOV-5)
    completion.py      Deliver ready and complete, the receipt, reopen, the final gap review
    bets.py            Explore bets, the time box, findings, the findings report
    cycles.py          Operate cycles, the roll, the scorecard, recurring requirements
    metrics.py         metric requirements, readings, losing ground
    speed.py           the time accounting and the speed flags
    operations.py      requirements.*, plan.*, commitments.*, bets.*, cycles.* for people
    agent_operations.py  the same verbs for the CEO, within its authority
  jobs/planning.py     re-projection, bet expiry, cycle roll, metric readings, speed flags
web/src/panels/plan/   the Plan panel
acceptance/scripts/    deliver, explore and operate reference crews
```

`domain/work/tasks.py` asks `planning.readiness` before a task is created. Nothing else in phase 4's code changes shape.

## Tables (migration 0012)

- `requirements`: project, text, author kind, state, test kind and test, estimate in runs, stage, recurring flag, metric target and source, failure count, ruling note.
- `requirement_dependencies`: requirement, depends on.
- `tasks.requirement_id` and `tasks.bet_id` (replacing the free-text link for new tasks).
- `commitments`: project, state, date, the settings version and scope fixed at acceptance, reset count; `target_dates`: date, source.
- `bets`: project, statement, kill condition, kill date, state, extension, finding artifact.
- `cycles`: project, number, opens, due, state, scorecard, narrative.
- `metric_readings`: requirement, value, at.
- `reserve_draws`: project, reason, arithmetic, drawn by, cancelled at; `raise_requests`: what, arithmetic, state.
- `gap_reviews` and `gaps`: reviewer, must-fix or nice-to-have, reason, state.
- `time_spans`: project, what the time went to (working, waiting on the chairman, on a limit or the budget, on a provider, reviewing), from, to.

The lifecycles in sections 7.2, 7.4, 7.6 and 7.13 are added to the drift test.

## Tests to write first

1. **INV-18 and INV-19 as property tests:** for any sequence of propose, accept, cut, add-dependency and stage moves, no task is ever created under a requirement that is not ready for work, and the graph stays acyclic.
2. **The arithmetic as pure-function tables:** bias multiplier, plan tokens, throughput, projection, burn rate, reserve eligibility. Every refusal that cites arithmetic shows the numbers, and a test reads them back.
3. **Three golden-path scenarios,** one per project type, as scripted crews.
4. **The reserve:** drawn when at least 75% of accepted requirements are met and the rest fits; refused, with the arithmetic, when half done, when plan tokens are unknown, and a second time.
5. **Commitment re-projection:** a table of states against scope and dates; a property test that the date is only ever the projection or a chairman's date.
6. **Cycle roll:** completed, missed and skipped; resuming a long-paused project opens exactly one cycle.
7. **The speed criterion,** as an acceptance test with real time.
8. **Attack tests** for each new rule: an agent marking a requirement met, accepting its own scope without authority, writing a date, drawing the reserve twice, opening a bet late, and creating work against proposed scope.

## Review items I plan to apply

Marked "before phase 5" in `docs/spec-review.md` (question 4).

| Item | Change |
| --- | --- |
| R-24 | At 90% of the budget, new tasks may also serve a bet already active, not only a requirement in progress |
| R-40 | "Work has changed since the last ruling" means a task under the requirement reached done after it, or the workspace snapshot changed |
| R-44 | A metric requirement is met when a platform reading reaches its target; recurring ones reset at the cycle roll |
| R-45 | A cycle is skipped when no work run happened in it because the project was held or paused, and missed when work ran but recurring scope stayed open. `cycle.roll_day` 0 is Monday |
| R-46 | After an Explore reserve draw, only tasks serving active bets may be created and no bet may be opened. A Deliver draw is refused when plan tokens are unknown |
| R-55 | INV-18 reads: no task is created under a requirement that is not ready for work, and no open task remains under a cut one |
| R-58 | The chairman may move a commitment's date; it becomes accepted again |
| R-61 | A CEO adds scope to a ready project only through a chairman directive |
| R-62 | The chairman can complete an Operate project, with a final scorecard, instead of stopping it |

R-57 (a proposal declined when nobody answers in time) waits for decision items in phase 6.

## Rules that start in warn-only mode (NFR-20)

None. They guard scope, dates and budget, and INV-18 and INV-19 are invariants.

## Risks

- **Size.** This phase is about as large as phase 2. See question 1.
- **Arithmetic nobody can check by eye.** Every figure the product shows or refuses with (projection, plan tokens, reserve) is computed by one pure function and tested as a table.
- **Real-time tests.** The speed criterion needs wall-clock time. It lives in `tests/acceptance/` with a small crew, so the fast suite stays fast.
- **Scripted crews need requirement and task ids.** A new project's ids are predictable in a fresh database; the reference scripts depend on that, as phase 4's do.

## Owner answers (22 Nov 2026)

| Question | Answer |
| --- | --- |
| Review stops | **One stop, at the full exit demo** |
| Metric requirements before data sources exist | A public URL and a pattern, fetched through the guard |
| "Questions never block" (SPD-5) | **Moved to phase 6,** with question items |
| Review items R-24, R-40, R-44, R-45, R-46, R-55, R-58, R-61, R-62 | Accepted as recommended; applied in spec revision 2.15 |
| The Plan panel | Built in this phase, as the Board was in phase 4 (not asked again) |

No open questions remain.
