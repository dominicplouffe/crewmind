## 7. State machines

Every lifecycle is declared once, here. A transition not listed is refused. Each transition writes an event naming its actor (INV-21). The tables are the source for the implementation's enumerated states. A lifecycle that is not in this section must not be implemented: add its table here first, in the same change.

**Who.** In the Who columns:

- **Chairman** means the chairman or a co-chair, except for deleting a project and handing on the chair, which only the chairman may do (section 3).
- **Platform** means a named platform job (BG-4).
- **Agent** names the seat kind where it matters (CEO, lead, claimant, reviewer seat).

### 7.1 Project

A project has a lifecycle state, plus a set of active **hold reasons**. The reasons decide whether a project is running, held or paused, and each reason is lifted only by its own trigger.

| Hold reason | Added when | Lifted by |
| --- | --- | --- |
| `chairman` | `/hold`, optionally with a lift time (PRJ-2) | `/resume` (Chairman); the lift time arrives (Platform) |
| `budget_wall` | Spend reaches the wall and no reserve draw is eligible (GOV-3, GOV-10) | A budget raise that puts the wall above spend (Chairman); a reserve draw (CEO or Platform, GOV-10); the Operate monthly reset (Platform) |
| `auth_failures` | 3 consecutive authentication failures on a provider (PRJ-2, LLM-11) | `/resume` (Chairman), refused until the credential passes a smoke check (LLM-10) |
| `skipped_cycles` | 2 consecutive skipped Operate cycles (PRJ-8) | `/resume` (Chairman) |

- With no reasons, a started project is **running**. With only `chairman`, it is **held**. With any platform reason, it is **paused**, whether or not `chairman` is also present.
- `/resume` lifts `chairman`, `skipped_cycles` and `auth_failures` (once the credential passes). It is refused while `budget_wall` holds, with the arithmetic (GOV-9).
- A held project can also become paused, for example when chat runs reach the wall.
- Stop and delete clear every hold reason.

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| draft | running | Start (PRJ-1 checks pass) | Chairman; Founder in quick mode |
| running | held | `chairman` reason added | Chairman |
| running, held | paused | A platform reason added | Platform |
| paused | held | The last platform reason lifted while `chairman` remains | Chairman; platform |
| held, paused | running | The last hold reason lifted | Chairman; platform |
| running | ready | Deliver only: PRJ-4 conditions met | Platform |
| ready | running | Scope added or reopened; a CEO reaches this only through a chairman directive (INV-20) | Chairman; CEO with plan or scope authority |
| ready | completed | Sign-off, or `completion.auto_after` elapses | Chairman; platform |
| running, held | completed | Explore only: the chairman ends it | Chairman |
| running, held, paused | completed | Operate only: the chairman completes it, with a final scorecard | Chairman |
| completed | running | Reopen within `reopen.window` | Chairman |
| draft, running, held, paused, ready | stopped | Stop (terminal) | Chairman |
| draft, stopped, completed | deleting | Delete (two steps, human-only) | Chairman only |
| deleting | its prior state | Cancel within `delete.grace` | Chairman only |
| deleting | deleted | `delete.grace` elapses; everything purged | Platform |

Held and paused projects lease no work runs and change no work state (INV-20). They differ in cause and in display: held is the chairman's choice, paused is automatic. Every active hold reason is shown with what lifts it (EXE-4).

**Which runs may lease in each state.** Runs of a kind the state does not allow are not leased, and queued ones are dropped (EXE-5).

| State | Work runs | Chat runs | Check runs |
| --- | --- | --- | --- |
| draft | no | no (Founder drafting is not a project run) | no |
| running | yes | yes | yes |
| held | no | yes | no |
| paused, `budget_wall` among the reasons | no | no; the platform answers with a status card (GOV-3) | no |
| paused, other reasons only | no | yes | no |
| ready | no | yes (PRJ-5) | no |
| completed | no | yes | no |
| stopped, deleting | no | no | no |

On entering a state that forbids a run kind, live runs of that kind are revoked (EXE-9). The one exception is the budget wall: in-flight runs finish within `run.max_tokens` (GOV-3).

### 7.2 Requirement

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | proposed | Propose | CEO |
| (new) | accepted | Add | Chairman (chairman-authored) |
| proposed | accepted | Accept (PLN-3 fits the budget) | Plan authority |
| proposed | declined | Decline, with a reason | Plan authority |
| proposed | declined | Not accepted by the decision item's deadline (HUM-2) | Platform |
| accepted | in progress | First task under it claimed | Platform |
| in progress | checking | PLN-10 conditions | Platform |
| checking | met | Command test passes, or verdict passes | Platform |
| checking | in progress | Test fails, or verdict rejects | Platform |
| accepted, in progress | cut | Cut, with a reason | Scope authority (CEO-authored); chairman (chairman-authored) |
| met, cut | accepted | Reopen | Scope authority (CEO-authored); chairman (any) |
| met | accepted | Cycle roll, recurring requirements only (PRJ-8) | Platform |

Cutting a requirement kills its open tasks (7.3).

### 7.3 Task

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | ready | Create (WRK-3, WRK-5 checks pass) | CEO (top-level); lead (subtask) |
| ready | claimed | Claim (WRK-4) | Lead or assignee |
| claimed | ready | Claim expiry (WRK-4) | Platform |
| claimed | checking | Complete, command test | Claimant |
| claimed | review | Complete, observable test | Claimant |
| claimed | done | Complete, observable test, solo with independent read off ("self-reported", P5) | Claimant |
| checking | done | Pinned check exits 0 | Platform |
| checking, review | ready | Check fails, or review rejects, with fewer than 3 failures; reserved for its previous claimant | Platform |
| checking, review | blocked | Third failure | Platform |
| review | done | Review ok | Reviewer seat |
| review | closed unread | No reviewer seat remains | Platform |
| claimed | blocked | Block, with a reason | Claimant |
| ready, claimed | blocked | The bet it serves expired (PRJ-7) | Platform |
| ready, claimed, blocked | killed | Kill, with a reason | CEO (top-level); lead (own subtasks) |
| ready, claimed, blocked | killed | The requirement it serves was cut | Platform |

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
| open | decided | A typed action | Chairman; MCP within scope; person via Slack |
| open | open (new deadline) | Extend, 1–30 days, with a reason (approvals) | Chairman |
| open | defaulted | Deadline passes; the declared default applies. This includes an audit sample expiring as "not reviewed" and a green status review closing itself | Platform |
| open | withdrawn | Withdraw | Filer |
| open, raised | void | Project stopped | Platform |

Kind-specific states:

| Kind | From | To | Trigger | Who |
| --- | --- | --- | --- | --- |
| Flag | open | raised | Raised in the chat with a proposal (HUM-6) | CEO |
| Flag | raised | acknowledged | Acknowledge | Chairman |
| Flag (state) | open, raised, acknowledged | cleared | The condition no longer holds | Platform |
| Heads-up | open | acknowledged | Acknowledge | Chairman |
| Heads-up | open | archived | 7 days unacknowledged; listed in the daily brief | Platform |
| Mistake report | open (owed) | filed | Filed with the HUM-8 fields; cannot be edited afterwards | CEO |

An event flag closes at acknowledged. A state flag closes only at cleared, even if raised and acknowledged before. Which flag kinds are state flags is listed in HUM-6.

### 7.6 Commitment (Deliver)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | proposed | Propose (no date field) | CEO |
| proposed | accepted | Accept, at the projection or a later chairman date | Date authority |
| proposed | declined | Decline, with a reason | Date authority |
| proposed | declined | Not accepted by the decision item's deadline (HUM-2) | Platform |
| accepted, at risk, breached | at risk, breached, met, accepted | Re-projection (PLN-7) | Platform |
| at risk, breached | accepted | Reset to the current projection | Date authority |
| accepted, at risk, breached | accepted | Move the date to a chairman date (PLN-8, HUM-9) | Chairman |

### 7.7 Run

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | queued | Wake trigger (EXE-2), or a chairman message (chat) | Platform |
| queued | dropped | The project state no longer allows this run kind (7.1); wake reasons are re-derived later | Platform |
| queued | leased | Lease (EXE-5) | Runner |
| leased | failed | Seat check fails at lease (LLM-6) | Runner |
| leased | running | Sandbox started | Runner |
| leased | reaped | Lease TTL expired before the sandbox started | Platform |
| leased | killed | Revoked before the sandbox started | Platform |
| running | finished | Normal end | Runner |
| running | failed | Error; retried per EXE-8 | Runner |
| running | killed | Kill, hold, or a pause other than the budget wall (GOV-3) | Platform |
| running | terminated | Refusal cap | Platform |
| running | reaped | Stale heartbeat, or `run.timeout` exceeded | Platform |

### 7.8 Person account (ACC)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | invited | Invite (ACC-4); or bootstrap the first admin from the host, which prints a setup link (IF-4.2, NFR-2) | Admin; host operator |
| invited | active | Setup link used and a password set (ACC-1) | The person |
| active | deactivated | Deactivate; ends every session and revokes every token. Refused while the person chairs a project (ACC-5) | Admin |
| deactivated | active | Reactivate | Admin |

The instance role (`admin` or `member`) is a field, changed by an admin through promote and demote. It is not a state. Login lockout (ACC-1) is kept per address, known or unknown, so it is not an account state either.

### 7.9 Single-use link (invite, password reset)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | unused | Issue (ACC-4) | Admin; host operator (reset link, IF-4.2); the person (reset request) |
| unused | used | Followed once | The person |
| unused | expired | 72 hours pass | Platform |

### 7.10 Credentials of people and clients

**Browser session** (ACC-2, IF-3.7):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Sign in | The person |
| active | ended | Sign out; password change; 3 idle days; 14 days old; account deactivated | The person; platform |

**Personal token and MCP client token** (ACC-3, IF-5.1):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Mint, named, with an expiry (personal) or scopes (MCP) | The person (human-only for MCP tokens) |
| active | expired | Expiry date passes | Platform |
| active | revoked | Revoke; account deactivated | The person; admin; platform |

**MCP confirm token** (IF-5.3):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | unspent | First call of an irreversible write returns a preview | Platform |
| unspent | spent | Second call with the same tool and argument hash | MCP client |
| unspent | expired | 5 minutes pass | Platform |

### 7.11 Project membership (ACC-5)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | co-chair or observer | Add a member (human-only, IF-5.6) | Chairman |
| (new) | chairman | Create a project; the creator becomes its chairman | Any active member |
| co-chair, observer | co-chair, observer | Change role | Chairman |
| co-chair, observer | removed | Remove; effective on the member's next request | Chairman |
| chairman | co-chair | Hand on the chair; the new chairman takes the chairman role in the same transaction. In a break-glass hand-on, a person who is not yet a member joins as a co-chair first | Chairman only; admin as break-glass (section 3) |
| co-chair, observer | chairman | Receive the chair | (same transaction) |

A project always has exactly one chairman.

### 7.12 Team and seat (EXE-1)

**Team:**

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Hire (within `teams.max`) | CEO; chairman |
| active | stood down | Stand down; refused while the team holds open work; for a reviewer seat, refused if it is the last one and independent read is on (WRK-9) | CEO; chairman |
| active | stood down | Its stand-down condition becomes true and it holds no work (PLN-12) | Platform |
| stood down | active | Recall, with its history intact | CEO; chairman |

**Seat:**

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Its team is hired, or the CEO seat is created with the project | CEO; chairman; platform |
| active | paused | The seat check fails (LLM-6), for example its model was retired or no credential pays it | Platform |
| paused | active | The seat check passes again | Platform |
| active, paused | stood down | Its team is stood down | (as the team) |
| stood down | active | Its team is recalled | (as the team) |

A paused seat is never woken. The reason shows on its seat card (EXE-4).

### 7.13 Cycle (Operate)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | open | Project start, the previous cycle's roll, or resuming into one new cycle (PRJ-8) | Platform |
| open | completed, missed or skipped | Cycle roll | Platform |

At most one cycle is open.

### 7.14 Artifacts (ART)

The artifact status label (draft, in review, verified, delivered; ART-1) is derived when read, from the tasks and requirements the artifact claims and from its audience (WRK-15). It is not stored state, so it has no table. The lock is stored:

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| unlocked | locked | `/lock` (ART-5) | Chairman |
| locked | unlocked | Unlock | Chairman |

### 7.15 Evidence (WRK-12, INT-1 to INT-3)

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | pending | File (agent-claimed) | Agent |
| (new) | verified | Signed webhook event (platform-attested) | Platform |
| pending | verified | The verifier's checks pass | Platform |
| pending | failed | A check fails, or the fetch fails 5 times (fails closed) | Platform |

### 7.16 Side effect, launch and watch (WRK-16, WRK-17)

**Side effect:**

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | declared | Declare, with an idempotency key; a duplicate key returns the existing record | Agent |
| declared | finished | Finish, recording what happened (fired or failed) | The declaring agent, in that run or any later one |
| declared | finished | Close as outcome unknown, when its agent can no longer say | Chairman |
| finished | retired | Retire a launch; ends its watch | The launching seat; CEO; chairman |

**Watch:**

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | passing | Launch finished with its watch declared | Platform |
| passing | failing | The watch check fails; opens a watch-failing flag | Platform |
| failing | passing | The watch check passes | Platform |
| passing, failing | ended | Its launch is retired | Platform |

### 7.17 Conversation (MSG, CHAT)

**Directive** (MSG-3):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | issued | `/do`, or "Do it" on an action card | Chairman |
| issued | waiting | It changes work state and the project is held or paused (INV-20) | Platform |
| waiting | issued | The project returns to running | Platform |
| issued | done | The addressee reports it carried out, citing it | Addressed agent |
| issued, waiting | void | Project stopped | Platform |

**Action card** (CHAT-7):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | open | Post | Agent |
| open | accepted | "Do it", optionally after "Edit"; creates a directive | Chairman |
| open | dismissed | "Not now" | Chairman |

**Standing order** (MSG-4):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | proposed | Pin a message (the platform proposes the sentence), or the CEO proposes one | Chairman; CEO |
| proposed | active | Confirm or edit, within the limit of 25 active | Chairman |
| proposed | discarded | Discard | Chairman |
| active | retired | `/unpin`; stays listed as retired | Chairman |

**Closed decision** (MSG-5):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | closed | `/decide` | Chairman |
| closed | reopened | Reopen at any time; or a reopen request, with newer evidence, approved | Chairman |
| reopened | closed | A new ruling | Chairman |

**Correction** (MSG-6):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | `/fix` | Chairman |
| active | expired | `correction.ttl` elapses | Platform |
| active | removed | Remove | Chairman |

**Thread** (MSG-9, INT-10):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| open | frozen | Pair breaker or email loop guard | Platform |
| frozen | open | Unfreeze | Chairman |

**Chat session** (MSG-11):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | warm | A message addressed to the agent | Platform |
| warm | warm (restarted) | Its credential, grants, brief or standing orders changed | Platform |
| warm | held | A third involuntary restart in 10 minutes; the chairman is told why | Platform |
| held | warm | The next chairman message after the cause is fixed | Platform |
| warm | closed | `chat.keep_warm` passes with no message | Platform |

**Suggestion and notice** (WRK-2, EXE-2, EXE-8):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | pending | File a suggestion, or the platform posts a notice | Agent; platform |
| pending | delivered | Placed in a run's context pack | Platform |
| delivered | pending | That run failed; given back (EXE-8) | Platform |
| delivered | consumed | That run did not fail | Platform |

### 7.18 Models and credentials (LLM, INT)

**Model credential** (LLM-2):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Add | Chairman; admin |
| active | hidden | Hide, without deleting | Chairman; admin |
| hidden | active | Show | Chairman; admin |
| active, hidden | deleted | Delete; seats it paid for fail their seat check (7.12) | Chairman; admin |

**Circuit breaker**, per credential (LLM-11):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| closed | open | 3 consecutive transient failures | Platform |
| open | half-open | The cool-off elapses (5 minutes, doubling up to 1 hour) | Platform |
| half-open | closed | The probe succeeds | Platform |
| half-open | open | The probe fails; the cool-off doubles | Platform |

**Data-source tool permission** (INT-4):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | allowed | Classified as a read tool when the source is added | Platform |
| (new) | denied | Classified as a write or unknown tool | Platform |
| denied | allowed | Allow, directly or by approving an agent's request (human-only for write-capable tools, IF-5.6) | Chairman |
| allowed | denied | Deny | Chairman |

**Connection** (CON-1, CON-2):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Added | Owner; admin (install); chairman (project) |
| active | expired | Its expiry date passes; seats that used it are held | Platform |
| active, expired | active | Value replaced, or expiry date moved | Owner |
| active, expired | deleted | Deleted, after the projects that use it are listed; their seats that depend on it are held | Owner |

**MCP server** (CON-9 to CON-11):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Added and its test passes | Owner |
| (new), active | needs sign-in | OAuth sign-in not done, or a refresh is refused | Platform |
| needs sign-in | active | Signed in again | Owner |
| active | failing | The circuit breaker opens (LLM-11) | Platform |
| failing | active | The half-open probe succeeds | Platform |
| any but deleted | deleted | Deleted | Owner |

**Need**, per project (CON-5):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | open | Declared by a role, a spec or an approved agent request | Platform; chairman |
| open | met | A connection is attached and granted to the roles that need it | Chairman |
| open | waived | The project starts without it; the seats that need it are held | Chairman |
| waived | met | The connection is attached; the holds lift | Chairman |
| met | open | The connection is detached, revoked, deleted or expires | Chairman; owner; platform |
| open, waived | dropped | The roles that needed it leave the roster | Chairman; CEO |

**Mailbox**, project or agent (INT-6, INT-10):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | active | Managed: created by the mail provisioner. Manual: connected by the chairman. Test send and receive pass | Platform; chairman |
| active | disabled | Project stopped (managed), or its seat stood down | Platform |
| disabled | active | Its seat recalled | Platform |
| active, disabled | deleted | Managed only: the project's `delete.grace` ends | Platform |
| active, disabled | disconnected | Manual only: project deleted or the chairman disconnects it | Platform; chairman |

### 7.19 Founder and library (FND, LIB)

**Drafting conversation** (FND-1, FND-5, FND-12):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | drafting | Start a project in chat, CLI or MCP | Person |
| drafting | created | The chairman confirms the ledger; the project is created in draft and the conversation becomes its chat | Chairman |
| drafting | discarded | The person who started it discards it. No project comes of it; the conversation stays in the record | Person |
| drafting | creating | Quick mode accepts all recommendations | Founder |
| creating | starting | The project is created | Founder |
| starting | started | The project is running | Founder |
| creating, starting | failed | Any step fails; nothing is left created | Platform |

**Skill version** (LIB-6):

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | in review | Added from a file, repository or URL, or proposed by the CEO | Admin; chairman; CEO |
| in review | approved | Approve, after seeing every file (human-only) | Admin; chairman |
| in review | rejected | Reject | Admin; chairman |
