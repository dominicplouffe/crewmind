## 8. Invariants

These must hold at all times, under any sequence of API calls, crashes and retries. Each one needs an attack test (P10). Chaos tests kill workers, drop database connections and race runners against each one. Invariants add no rules of their own: each restates a requirement it cites.

**Authority**

- **INV-1** No agent action writes any of the following (P7, P5, MSG-3):
  - a requirement as met;
  - a commitment date or status;
  - a setting;
  - a standing order, closed decision or correction;
  - a tool permission, an email allowlist entry or a credential value;
  - a revenue line or a metric reading;
  - a verdict on its own work;
  - an acknowledgement of its own flag;
  - a change to a locked artifact;
  - a change to chairman-authored scope.
- **INV-2** No task reaches done on a command test except by a platform-run check of the pinned command that exited 0 (WRK-5, WRK-7).
- **INV-3** No agent completes, reviews or gives the verdict on work it did, and no agent claims a task whose success test it wrote while another active agent exists (P5, WRK-4, WRK-9). Solo projects are exempt and labelled, for observable tests only (P5).
- **INV-4** A run token works only for its own run, agent and project, and only while the run is live and not revoked.
- **INV-5** A person or client that cannot see a project gets the same answer as for a project that does not exist.
- **INV-6** No secret value, provider key included, appears in any sandbox, agent-facing response, export, clone, spec, rehearsal or log. The only exception is role credentials granted by name (EXE-13), plus the stated subscription-harness exception (LLM-8).
- **INV-7** Agent-written text is always wrapped as untrusted when it reaches a person's AI client.

**Budget**

- **INV-8** Every model call has a ledger line, whatever the run's ending (P9, LLM-9).
- **INV-9** Token spend never exceeds the wall by more than the tokens of runs already in flight when it was crossed, each bounded by `run.max_tokens`. At the wall, nothing new is leased for that project (GOV-3). The wall moves only by a chairman change or a single eligible CEO reserve draw (GOV-10).
- **INV-10** Real-world spend never exceeds `spend.monthly_cap`, counting committed but unfinished purchases (GOV-8).
- **INV-11** A project with no wake trigger (EXE-2) and no message from a person spends 0 tokens (P8).

**Execution**

- **INV-12** At most one runner holds a given run, and no run is both queued and running.
- **INV-13** At most one queued or running work run per agent; nothing new is leased while the number of work runs is at or above `run.concurrency`. Lowering the limit never kills a live run.
- **INV-14** A side effect recorded under an idempotency key fires at most once, across any number of retries.
- **INV-15** A late result from a reaped worker changes nothing.
- **INV-16** A claimed task always has a live run behind it or a path back to ready (WRK-4).

**Decisions and scope**

- **INV-17** A decision item reaching its deadline always resolves to its declared default (HUM-2). Tool permissions never resolve to allow.
- **INV-18** Proposed scope never has work against it; no task is created under a requirement that is not ready for work, and no open task remains under a cut one (PLN-2).
- **INV-19** The requirement graph is always acyclic, and where stages are used, work never runs ahead of the lowest open stage.
- **INV-20** A held, paused, stopped, ready or completed project changes no work state.
- **INV-21** Every state change appears in the event log with its actor (person, person via MCP or Slack, agent, or platform job), time, before and after.
- **INV-22** The agenda's next time-based wake (heartbeat, not-before, deadline, cycle roll, watch) equals the dispatcher's. Wakes caused by messages cannot be predicted and are not compared.

**Conversation**

- **INV-23** A chat run changes no state except posting, writing its own memory notes, and carrying out a directive it cites (CHAT-6, MSG-3).
- **INV-24** Every chairman message receives an agent reply or a platform status within 60 seconds (P17, CHAT-3).
- **INV-25** Every active standing order, closed decision and correction that concerns an agent is present, verbatim, in every context pack that agent receives (P16, MEM-1).
- **INV-26** A closed decision is reopened only by the chairman, or by a reopen request that links evidence newer than the decision (MSG-5).
