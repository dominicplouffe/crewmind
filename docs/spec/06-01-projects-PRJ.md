### 6.1 Projects and the three project types (PRJ)

Every project has one of three types, chosen at creation and never changed. Rules differ by type, so the type is a first-class field the rule engine reads.

|  | **Explore** | **Deliver** | **Operate** |
| --- | --- | --- | --- |
| Shape | Find out something: "is there demand for…", "one sale in 7 days" | Ship one defined thing, then finish | A rhythm that repeats: a weekly digest, a morning inbox sweep |
| Unit of scope | Bets, each with a kill condition and kill date | One-off requirements | Recurring requirements due every cycle, plus one-off ones |
| Work may start on | An active bet | An accepted, estimated requirement whose dependencies are met | The same as Deliver, within the open cycle |
| Speed | Time box `explore.timebox` \[7 days\]; bets default to `bet.window` \[48 h\] | As soon as possible; a first usable version first (SPD-4) | Each cycle's due time |
| Date | The time box. When it passes, the findings report is assembled and the chairman ends or extends the project; nothing pauses | Optional chairman target; the **commitment** is computed (PLN-5) | No project date. Each cycle has its own due time |
| Ends | When the chairman decides, with a findings report | When all scope is met and the final gap review passes (PRJ-4) | Never by itself. Pauses after 2 consecutive skipped cycles |
| Progress shown as | Verified evidence and findings per bet | Requirements met, projection, deliverables | Per-cycle scorecard: "met in 23 of the last 24 cycles" |
| Plan adversary seat | Optional | Always staffed | Always staffed |

- **PRJ-1 Lifecycle.** Project states and transitions are defined in section 7.1. Start is refused for stopped or completed projects, for seats that cannot run (LLM-6), for projects whose budget is spent, and for projects that need email when it is not working.
- **PRJ-2 Hold.** `/hold` pauses with an optional resume time ("until Sunday 09:00"), recorded with a reason. At the resume time the project resumes automatically. A held project leases no work runs, so work stops mechanically, not by request. The chairman can still chat. The system also pauses automatically at the budget wall (GOV-3), after 3 consecutive authentication failures on a provider, and after 2 skipped Operate cycles. Each cause is a separate hold reason, lifted only by its own trigger (section 7.1); `/resume` is refused while the budget wall holds, with the arithmetic. A hold or pause purges queued work runs. A hold, and every pause except the budget wall, also revokes live work-run tokens; at the wall, in-flight work runs finish within their per-run cap (GOV-3). On resume, the pause reason is placed in the CEO's next context pack.
- **PRJ-3 Stop** is terminal. It revokes all runs and voids every pending decision item with a deny-shaped outcome.
- **PRJ-4 Deliver: ready and complete.** A Deliver project becomes **ready** when every accepted requirement is met, the final gap review has no open must-fix items (WRK-11), and no top-level task is open. The moment it is ready, the platform posts the deliverables in the chat. The chairman signs off, or the project completes after `completion.auto_after` \[24 h\] (0 turns this off) unless scope changes first. Completion writes a **receipt**:
  - for each requirement, estimated versus actual runs and tokens;
  - total tokens, broken down by kind, and any CEO reserve drawn;
  - wall-clock time and where it went (SPD-8);
  - whether the commitment was kept.
- **PRJ-5 Ready projects spend nothing** except chat runs the chairman starts.
- **PRJ-6 Reopen** is allowed within `reopen.window` \[14 days\] of completion; after that the answer is "clone it".
- **PRJ-7 Explore.** Bets expire at their kill date and their open tasks block. The chairman may extend a bet once, with a reason, to a future date. Evidence counts only once verified (WRK-12). Every ended bet gets a finding, written by the CEO and published as an artifact: confirmed, killed or inconclusive, with its evidence. When the time box ends or the chairman ends the project, the platform assembles a findings report from those findings. **Promote to Deliver** creates a draft Deliver project from the findings, through the Founder.
- **PRJ-8 Operate cycles.**
  - The cycle length is `cycle.period` \[weekly\], rolling on `cycle.roll_day` (0–6 for weekly, 0 = Monday; 1–28 for monthly and quarterly; 29–31 are refused) and due at `cycle.due_time` \[the end of the cycle\]. A cycle-specific due time with a cited source overrides the calendar.
  - At roll the system:
    - closes the cycle as completed, missed or skipped;
    - writes the scorecard, and a stub narrative if the CEO wrote none;
    - carries unfinished one-off scope forward and reopens recurring requirements;
    - gives the CEO the last 3 cycle narratives verbatim.
  - A paused Operate project resumes into exactly one new cycle, however many it missed.
  - A cycle is **skipped** when no work run happened in it because the project was held or paused, and **missed** when work ran but recurring scope stayed open at the due time.
  - The chairman can complete an Operate project, with a final scorecard, so a finished operation does not have to be stopped.
- **PRJ-9 Clone and export.** Clone copies the settings, roster, pinned role versions, standing orders and credential grants, but no history and no mailbox. Export produces a spec (LIB-4) with no secret values.
- **PRJ-10 Delete.** Deleting a project is chairman-only and human-only (IF-5.6), and needs two steps. An export is offered first. After `delete.grace` \[7 days\] the platform purges everything: event log, chat, memory, artifacts, traces, workspace and any managed mailbox (INT-6).
