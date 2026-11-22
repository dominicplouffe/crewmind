### 6.9 Decision items and reporting (HUM)

- **HUM-1 One decision-item type.**
  - Every item that waits on a human has:
    - a kind and the filer;
    - a title built from typed fields (never from agent-supplied text that could carry markup or commands);
    - a recommendation (10–300 characters) and what happens if declined;
    - a deadline and the default outcome applied at it;
    - typed actions;
    - the basis of any figure (WRK-10);
    - an optional chairman note and a full history.
  - A new kind is a registration. It appears automatically in the desk, the chat as a card, Slack, the daily brief, the agenda, the API, the CLI, MCP and notifications (IF-1.3).
- **HUM-2 Kinds.**

| Kind | Filed by | Deadline (default) | At the deadline |
| --- | --- | --- | --- |
| Approval: spend | CEO | `approval.window` \[7 days\] | Deny |
| Approval: legal | CEO | 7 days | Deny |
| Approval: tool permission | Any agent | 7 days | Deny (never allow) |
| Approval: capacity (budget, concurrency) | CEO | 7 days | Deny |
| Assist (a step only a human can do: captcha, 2FA, identity check, login) | Any agent | 7 days | Deny; the task stays blocked |
| Question | CEO | `question.window` \[24 h\], at most 72 h | The CEO's stated default stands |
| Heads-up | CEO | None | Archived unacknowledged after 7 days, and listed in the daily brief |
| Flag | Platform | None while the condition holds | Stays until the condition clears |
| Budget checkpoint | Platform (GOV-3) | 24 h | Land: wrap up within the remaining budget |
| Proposed scope (only when the chairman holds plan authority) | CEO | 72 h | Not accepted |
| Proposed commitment (only when the chairman holds date authority) | CEO | 72 h | Not accepted |
| Verdict (only when the chairman holds verdict authority) | Platform | 72 h | Passed to an independent reviewer seat |
| Audit sample | Platform | `audit.window` \[48 h\] | Expires as "not reviewed" |
| Reopen request | Any agent | 7 days | Deny |
| Mistake report | Platform opens; CEO files | FYI once filed | Stays owed until filed |
| Status review | Platform | 24 h if green | Green reviews close; others stay open |
| Delivery sign-off | Platform (PRJ-4) | `completion.auto_after` \[24 h\] | Complete |
| Reserve draw (only when the chairman holds the draw verb) | CEO | 24 h | Deny |

- **HUM-3 Defaults and silence.** Only delivery sign-off and green status reviews conclude positively by default; both close bookkeeping (P6). Approval deadlines can be extended by 1–30 days with a reason; decided items cannot be extended. Approving a capacity or tool-permission item applies it. Spend, legal, tool-permission, assist and capacity items stay with the chairman at every authority setting.
- **HUM-4 Don't ask about what you hold.** An approval, question or proposal whose subject is a verb the CEO holds under the authority dial is refused: "You hold this decision. Decide it and post a heads-up." Questions carry a required `concerns` field naming the decision verb they concern, or "other". The rate of "other" per CEO is shown in the run health report.
- **HUM-5 Questions** (CEO only).
  - Each needs:
    - a why of 20 or more characters;
    - up to 4 options and a recommendation;
    - a window;
    - the default the CEO will act on (20 or more characters).
  - At most `question.max_open` \[3\] are open at once.
  - The CEO proceeds on its default at once (SPD-5).
  - The default must be an action within the CEO's current authority. It may not spend, grant a permission or widen scope (P6). It is checked with the `concerns` field (HUM-4).
  - The chairman answers by picking an option or replying in the question's thread.
  - One reminder goes out halfway through the window. At the deadline the question lapses and the default stands on the record.
- **HUM-6 Flags** open from arithmetic only. One live flag per condition. The CEO closes a flag only by raising it in the chat with a proposal; the chairman acknowledges raised flags. A **state** flag stays open until its condition clears, whatever is said about it. An **event** flag records something that happened and closes when it is raised and acknowledged. The kinds:

| Flag | Type | Opens when |
| --- | --- | --- |
| Recurring requirement missed | event | A recurring requirement is open at its cycle's due time |
| Cycle missed | event | An Operate cycle closes as missed |
| Deadline at risk | state | The commitment is at risk or breached (PLN-7) |
| Losing ground | state | PLN-11 |
| Work starved | state | A cap blocked claimable work for an hour |
| Self-gated | state | Only the CEO's own not-before times block work |
| Budget wrap-up | state | Spend reaches `budget.wrapup_at` |
| Spinning | state | GOV-7 |
| Slow start | state | SPD-3 |
| No visible output | state | SPD-4 |
| Seat idle | state | SPD-9 |
| Watch failing | state | WRK-17 |
| Stall | state | EXE-16 |
| Listening | event | An agent's corrections exceed `listening.flag_at` \[3\] in 7 days |
| Mistake report owed | state | A mistake report is unfiled 24 h after it was opened |

- **HUM-7 Assists.** Any agent may file a step only a human can do. The task waits; the rest of the project does not.
- **HUM-8 Mistake reports.** The platform opens a mistake report when the chairman marks a correction "this cost us", when an audit sample fails, or when a commitment is breached. The CEO files:
  - what was wrong;
  - the tokens it cost, which the platform computes;
  - the cause;
  - the fix;
  - the prevention, which is saved as a pinned lesson (MEM-1).

  A filed report cannot be edited.

  The cost is the tokens of the run that wrote the corrected reply, of the runs that changed the audited task, or of everything spent since the breached commitment was accepted.
- **HUM-9 Status reviews.**
  - The platform builds one every `review.every` \[7 days\], or at the cycle roll for Operate projects with weekly or longer cycles. It costs 0 tokens, even with an empty board or a spent budget.
  - It holds a frozen snapshot of the numbers beside the previous review's decisions and what they bought.
  - The CEO may add a narrative answering each item of the previous plan. If none is written, the review says so.
  - The chairman has six levers, each recorded with a reason: cut, add, reword, move the date, raise the budget, accept the slip.
  - A green review (nothing at risk, no failed audit, within budget) closes itself after 24 hours.
  - Reviews never block work.
  - A lever records the chairman's decision and reason on the review; the change itself is made with its own operation. A review on which a lever was used no longer closes itself. Green also means no flag is open.
- **HUM-10 Desk.** One definition of "waiting on you" used everywhere: pending approvals, open questions, proposed scope, owed verdicts, an unaccepted commitment, a delivery awaiting sign-off, expired bets, frozen threads, budget checkpoints. Snoozing is per person and cannot outlast the item's deadline; an item with no deadline returns within 7 days. Flags, heads-ups, status reviews and mistake reports are not on the desk: they are in the brief.
- **HUM-11 Daily brief.**
  - Built from the record at 0 tokens and sent once per local day at `brief.time` \[08:00\] in the person's `person.timezone` for running, held and paused projects. It is on by default.
  - Sections:
    - worth your eye;
    - what moved;
    - what the CEO handled itself, worst first;
    - what decided itself (expired approvals, lapsed questions, auto-completion, cycle rolls, pauses);
    - what happens next.
  - It separates requirements settled from tasks closed.
  - Until mail exists (phase 8) the brief is shown in the app and announced by a browser push. A person with no running, held or paused project gets none.
  - Scheduled reports are platform jobs that fire on time. If an agent narrative is late, the report goes out without it and says so.
- **HUM-12 Agenda.** The next `agenda.days` \[14\] days (at most 90), at 0 tokens, in the project's timezone:
  - heartbeats and when they will skip;
  - deadlines with their consequences;
  - kill dates and the time box;
  - commitment versus projection;
  - cycle rolls, review dates and watch intervals;
  - budget reset.

  It must agree with the dispatcher's actual next wake (INV-22).
