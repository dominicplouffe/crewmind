# Phase 6 plan: the chairman loop

Goal (PLAN.md): the chairman sees everything that matters and is never left in silence.

**Exit demo.**

- The never-silent scenario passes: with the provider down, the budget at the wall, the project held, and a crash mid-reply, every chairman message gets a reply or a platform status within 60 seconds.
- The desk, the daily brief, since-you-were-away, the agenda and the alerts all agree with the event log.
- An MCP client with the steer and create scopes works, and an irreversible write needs two calls.

Status: **agreed with the owner on 22 Nov 2026.** The answers are at the end.

## What phase 6 covers

29 requirement ids: CHAT-15; GOV-8; HUM-1 to HUM-12; INT-7; INV-10, INV-17, INV-22; IF-5.1 to IF-5.8; NFR-13; WRK-10 (moved from phase 4); SPD-5 (moved from phase 5).

Until now, everything that waits on the chairman has been a chat line with a button in a panel. From this phase it is one thing, a **decision item**, with a deadline and a declared default, shown the same way everywhere.

## Five parts

Each part ends with the suite green on both databases.

| Part | Builds | Demo |
| --- | --- | --- |
| **6a Decision items** | The one item type with its lifecycle (7.5), deadlines and defaults, extension, withdrawal, "don't ask about what you hold" (HUM-1 to HUM-4, INV-17). The phase 5 stand-ins become items: proposed scope, proposed commitment, verdict, reserve draw, capacity raise, delivery sign-off, audit sample, reopen request, budget checkpoint | A proposal nobody answers is declined after 72 hours; a tool-permission item never resolves to allow; the CEO is refused an approval for a decision it holds |
| **6b Questions, assists and spend** | Questions that never block, with rework recorded against them; assists; heads-ups; figures need a basis; real-world spend with its cap and threshold (HUM-5, HUM-7, SPD-5, WRK-10, GOV-8, INV-10) | The CEO asks, proceeds on its default at once, and the answer arrives later; a purchase past the monthly cap is refused whatever was approved; an amount with no basis is refused |
| **6c Flags, mistakes and reviews** | Flags from arithmetic, one live flag per condition, state and event flags; mistake reports with their computed cost and pinned lesson; status reviews with six levers (HUM-6, HUM-8, HUM-9). The phase 4 and 5 guards and chat lines become flags | A breached commitment opens a mistake report the CEO must file; a green review closes itself; a state flag stays until its condition clears |
| **6d Desk, brief, agenda and alerts** | One definition of "waiting on you"; snooze; the daily brief; since you were away; the agenda that agrees with the dispatcher; alert levels by browser push and in the app (HUM-10 to HUM-12, CHAT-15, INT-7, INV-22) | The never-silent scenario; the brief, the desk and the agenda checked against the event log line by line |
| **6e MCP** | The steer, create and configure scopes; two-phase confirmation; attribution; the untrusted-content envelope; human-only verbs; the context budget; resources and prompts; OAuth 2.1 (IF-5.1 to IF-5.8, NFR-13) | An MCP client steers a project end to end; a delete needs a preview and a confirm token; the five OAuth attacks in IF-5.1 fail |

The web app gets a **Desk** (what waits on you, across projects), **decision cards in the chat**, and an **Agenda** tab in the Plan panel.

## What does not exist yet, and what stands in for it

| Later domain | Needed by | Stand-in in phase 6 |
| --- | --- | --- |
| **Slack** (phase 8) | Items as Slack cards; alerts in the project's Slack channel | Not built. The registration of a kind names Slack as a surface so it appears there when the bridge exists |
| **The Founder** (phase 7) | The create scope's tools (grade a goal, rehearse a spec, create from a spec, quick project); the doctrine and goal grammar served as MCP documents (IF-5.8) | The create scope covers what exists: create a project, clone is phase 7. The doctrine documents are served from the imported v1 content as they are |
| **Data sources and skills** (phase 8) | Tool-permission approvals; the configure scope's data-source and skill tools | The tool-permission kind is registered and its default (deny, never allow) is tested with a sample tool. The configure scope covers roster, budget, quality, settings and credential names |
| **Purchasing** (no integration yet) | GOV-8 needs something that spends money | An agent declares a purchase as a side effect with an amount; the cap and the threshold are enforced on that declaration |
| **Email** (phase 8, owner's choice) | Emailed alerts and briefs; the grace period and the daily email cap of INT-7 | Alerts and the brief go by browser push and in the app. The alert level setting is built; the email rules arrive with mail |

## Modules

```
src/crewmind/
  domain/decisions/
    model.py          item states (7.5), flag states, kinds as a registry
    kinds.py          one registration per kind: fields, actions, deadline, default, surfaces
    items.py          file, decide, extend, withdraw, default at the deadline, void
    questions.py      questions and their defaults; rework against a question
    assists.py        steps only a human can do
    flags.py          open from arithmetic, raise, acknowledge, clear
    mistakes.py       mistake reports and the pinned lesson
    reviews.py        status reviews: snapshot, narrative, six levers
    spend.py          real-world spend: cap, threshold, committed purchases
    desk.py           "waiting on you", snooze
    brief.py          daily brief and since-you-were-away, from the record
    agenda.py         the next days, from the same sources the dispatcher uses
    operations.py, agent_operations.py
  domain/integrations/
    alerts.py         levels and batching, by push and in the app
  surfaces/mcp/
    scopes.py, confirm.py, envelope.py, budget.py, resources.py
    oauth/            authorization code with PKCE, registration, tokens
  jobs/decisions.py   deadlines, flags, reviews, briefs, chasers
web/src/desk/         the Desk; web/src/chat/cards/ decision cards
```

Planning, work and budget stop posting their own "the chairman has been asked" lines and file items instead. That is the largest edit to existing code.

## Tables (migration 0013)

- `decision_items`: project, kind, filer, typed fields, recommendation, if-declined, deadline, default, state, outcome, chairman note; `decision_events` for the history.
- `flags`: project, kind, condition key, state, cause, opened, raised, acknowledged, cleared.
- `mistake_reports`, `status_reviews`, `purchases`, `snoozes`, `brief_runs`, `alert_sends`.
- `oauth_clients`, `oauth_codes`, `oauth_tokens` (hashes only), `mcp_confirm_tokens`.
- `project_guards` (phase 4) is folded into `flags`.

The lifecycles in section 7.5 are added to the drift test.

## Tests to write first

1. **INV-17 as a property test:** for any kind and any sequence of file, extend, snooze and clock moves, an item past its deadline is in its declared default, and a tool-permission item is never allowed.
2. **Parity (HUM-1, IF-1.3):** registering a sample kind makes it appear in the desk, the chat, the brief, the agenda, the API, the CLI and MCP, with no other code.
3. **Agreement with the record:** the desk, the brief, since-you-were-away and the agenda are rebuilt from the event log by a second, simple implementation in the test, and compared.
4. **INV-22:** the agenda's next time-based wake equals the dispatcher's, over random schedules.
5. **INV-10:** no sequence of declared and finished purchases exceeds the monthly cap.
6. **The never-silent scenario,** in-process and once on a real server.
7. **OAuth attacks:** PKCE stripping, code replay, redirect swap, audience confusion, scope widening, refresh-token replay.
8. **Attack tests** for each new rule: an agent deciding its own item, asking about what it holds, a fourth open question, editing a filed mistake report, closing a state flag by talking, an MCP client doing a human-only verb or widening its scope.

## Review items I plan to apply

Marked "before phase 6" in `docs/spec-review.md`.

| Item | Change |
| --- | --- |
| R-27 | A question's default must be an action within the CEO's current authority, and may not spend, grant or widen scope |
| R-33 | IF-5.6 and IF-5.2 become the sources: skill approval joins the human-only list; reopen, complete and edit memory join the steer scope |
| R-47 | Each flag kind is marked state (clears with its condition) or event (closes by raise and acknowledge) |
| R-48 | INV-22 compares only the next time-based wake: heartbeat, not-before, deadlines, cycle roll, watch |
| R-57 | A proposal nobody answers is declined at its deadline (held over from phase 5) |

R-60 (item states beyond the first table) is already in section 7.5.

## Carried in from phase 5

- **A chat run that ends with an empty reply is queued again for the same message.** Fixed in part 6d: it is part of never being left in silence, and it gets a cap.
- **The runner error** (`readuntil() called while another coroutine is already waiting`) is traced in part 6d.
- **The flaky browser test** ("earlier messages load a page at a time") is fixed with the Desk work.

## Rules that start in warn-only mode (NFR-20)

None planned. Deadlines and defaults are invariants.

## Risks

- **Size.** About as large as phase 5, and it rewires how three existing domains talk to the chairman.
- **OAuth is security code.** I will use the MCP SDK's own authorization-server support where it fits rather than write the protocol by hand, and test the five named attacks against it.
- **Time-based tests.** Deadlines, briefs and the agenda all depend on time zones and the clock; everything is driven with the test clock, never by waiting.

## Owner answers (22 Nov 2026)

| Question | Answer |
| --- | --- |
| Review stops | **One stop, at the full exit demo** |
| Review items R-27, R-33, R-47, R-48, R-57 | Accepted as recommended; applied in spec revision 2.17 (R-57 was already in sections 7.2 and HUM-2 and is built here) |
| Email | **Left to phase 8.** Alerts and briefs go by browser push and in the app. INT-7 will be partial: its email rules wait for mail |

No open questions remain.
