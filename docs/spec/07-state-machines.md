## 7. State machines

Every lifecycle is declared once, here. A transition not listed is refused. Each transition writes an event naming its actor (INV-21). The tables are the source for the implementation's enumerated states.

### 7.1 Project

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| draft | running | Start (PRJ-1 checks pass) | Chairman; Founder in quick mode |
| running | held | `/hold`, optionally with a resume time | Chairman |
| running | paused | Budget wall; 3 consecutive authentication failures; 2 skipped Operate cycles | Platform |
| held, paused | running | `/resume`; the resume time arrives; Operate budget reset | Chairman; platform |
| running | ready | Deliver only: PRJ-4 conditions met | Platform |
| ready | running | Scope added or reopened | Chairman; CEO with plan or scope authority |
| ready | completed | Sign-off, or `completion.auto_after` elapses | Chairman; platform |
| running, held | completed | Explore only: the chairman ends it | Chairman |
| completed | running | Reopen within `reopen.window` | Chairman |
| draft, running, held, paused, ready | stopped | Stop (terminal) | Chairman |
| draft, stopped, completed | deleting | Delete (two steps, human-only) | Chairman |
| deleting | its prior state | Cancel within `delete.grace` | Chairman |
| deleting | deleted | `delete.grace` elapses; everything purged | Platform |

Held and paused projects lease no work runs and change no work state (INV-20). They differ in cause and in display: held is the chairman's choice, paused is automatic.

### 7.2 Requirement

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | proposed | Propose | CEO |
| (new) | accepted | Add | Chairman (chairman-authored) |
| proposed | accepted | Accept (PLN-3 fits the budget) | Plan authority |
| proposed | declined | Decline, with a reason | Plan authority |
| accepted | in progress | First task under it claimed | Platform |
| in progress | checking | PLN-10 conditions | Platform |
| checking | met | Command test passes, or verdict passes | Platform |
| checking | in progress | Test fails, or verdict rejects | Platform |
| accepted, in progress | cut | Cut, with a reason | Scope authority (CEO-authored); chairman (chairman-authored) |
| met, cut | accepted | Reopen | Scope authority (CEO-authored); chairman (any) |

Recurring requirements return from met to accepted at each cycle roll (PRJ-8).

### 7.3 Task

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | ready | Create (WRK-3, WRK-5 checks pass) | CEO (top-level); lead (subtask) |
| ready | claimed | Claim (WRK-4) | Lead or assignee |
| claimed | ready | Claim expiry (WRK-4) | Platform |
| claimed | checking | Complete, command test | Claimant |
| claimed | review | Complete, observable test | Claimant |
| claimed | done | Complete, solo with independent read off ("self-reported") | Claimant |
| checking | done | Pinned check exits 0 | Platform |
| checking, review | claimed | Check fails, or review rejects, with fewer than 3 failures | Platform |
| checking, review | blocked | Third failure | Platform |
| review | done | Review ok | Reviewer seat |
| review | closed unread | No reviewer seat remains | Platform |
| claimed | blocked | Block, with a reason | Claimant |
| ready, claimed, blocked | killed | Kill, with a reason | CEO (top-level); lead (own subtasks) |

### 7.4 Bet (Explore)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Open (refused in the last 20% of the time box) | CEO |
| active | expired | Kill date passes; open tasks block | Platform |
| expired | active | Extend once, with a reason | Chairman |
| active, expired | confirmed, killed or inconclusive | Finding published | CEO |

### 7.5 Decision item

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | open | File | Per kind (HUM-2) |
| open | decided | A typed action | Chairman or co-chair; MCP within scope |
| open | open (new deadline) | Extend, 1–30 days, with a reason (approvals) | Chairman |
| open | defaulted | Deadline passes; the declared default applies | Platform |
| open | withdrawn | Withdraw | Filer |
| open | void | Project stopped | Platform |

### 7.6 Commitment (Deliver)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | proposed | Propose (no date field) | CEO |
| proposed | accepted | Accept, at the projection or a later chairman date | Date authority |
| proposed | declined | Decline, with a reason | Date authority |
| accepted, at risk, breached | at risk, breached, met, accepted | Re-projection (PLN-7) | Platform |
| at risk, breached | accepted | Reset to the current projection | Date authority |

### 7.7 Run

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | queued | Wake trigger (EXE-2), or a chairman message (chat) | Platform |
| queued | dropped | Project no longer running; wake reasons are re-derived later | Platform |
| queued | leased | Lease (EXE-5) | Runner |
| leased | failed | Seat check fails at lease (LLM-6) | Runner |
| leased | running | Sandbox started | Runner |
| running | finished | Normal end | Runner |
| running | failed | Error; retried per EXE-8 | Runner |
| running | killed | Kill, hold, pause or the wall | Platform |
| running | terminated | Refusal cap | Platform |
| running | reaped | Stale heartbeat, or `run.timeout` exceeded | Platform |
