### 6.2 Speed (SPD)

The owner's standing complaint about v1 was that projects, especially Explore and Deliver, took their sweet time. This section makes speed a requirement.

- **SPD-1 No clock waits on ready work.** When work is claimable and the budget and concurrency allow, a run starts within 10 seconds. There are no daily run plans, no hourly run caps, no inbox allowances and no "daily wake" schedules. The only throttles are the budget wall (GOV-3), `run.concurrency` \[4\], provider ceilings (LLM-12) and runaway guards (GOV-7).
- **SPD-2 Parallel by default.**
  - The CEO plans for parallel work, and the plan view shows the longest dependency chain.
  - The Founder staffs enough independent seats to use the concurrency.
  - Agent-to-agent messages wake an idle recipient immediately; they do not batch on a timer.
- **SPD-3 Start immediately.** On start, the CEO's first planning run is queued at once. Work begins as soon as the first requirement is accepted and estimated; the rest of the plan is written while work runs. There is no global plan gate. A Deliver project with no task claimed within `start.first_task_within` \[10 min\] raises a **slow start** flag naming the cause.
- **SPD-4 Ship early, then improve.** In a Deliver project, the Founder drafts, and the CEO keeps, a first requirement for a **first usable version** of the deliverable: the thinnest end-to-end thing the chairman can open. Running for `output.first_within` \[6 h\] with no deliverable version published raises a **no visible output** flag.
- **SPD-5 Questions never block.** When the CEO asks the chairman something, it proceeds at once on its stated default. If the answer differs, it adjusts, and the rework is recorded against the question.
- **SPD-6 Done means available.** Deliverables are in the chat the moment they are published and the moment a project is ready. The auto-completion delay (PRJ-4) only closes the books; it never delays access.
- **SPD-7 Explore is time-boxed.** Explore projects have a time box, bets default to short windows, and every bet ends with a finding (PRJ-7). In the final 20% of the time box, new bets are refused and the CEO's work goes to findings.
- **SPD-8 Speed is measured.** Every project shows, live and in its receipt:
  - time to first task, first deliverable and done;
  - where the time went: working, waiting on the chairman, waiting on a limit or the budget, waiting on a provider, and reviewing.

  Waiting on the chairman is shown separately, so slowness is attributed to the right party.

  The platform attributes each stretch of time when it ticks: a hold reason decides first (chairman or skipped cycles: the chairman; budget wall: a limit or the budget; authentication failures: a provider); then a live work run of a non-reviewer seat means working; a live reviewer run or a task in review or checking means reviewing; an open verdict, proposal or request only the chairman can answer, or a ready project, means waiting on the chairman; work runs queued with none live means a limit; anything else counts as working.
- **SPD-9 No idle crew.** Seats with no work are not woken (P8). A team seat that has closed nothing (no task done, no review given) in `seat.idle_after` \[3 days\] raises a **seat idle** flag; the CEO seat and the reviewer seat the platform staffs are not counted. The CEO stands the seat down or states, in the chat, what it is for.
