# Spec changelog

Newest first. One line per change, citing the ids touched.

## Revision 2.29 (23 Nov 2026): connections, part 7B.5

- **CON-11:** a command server is tested before it is saved, in a server started for the test and stopped after it; its variables name secrets or variables the person can see, read when it starts; it serves one call at a time.

## Revision 2.28 (23 Nov 2026): connections, part 7B.6

- **CON-13:** a changing tool's idempotency key is made from the server, the tool and its arguments, so the same change is made once per project; chat runs cannot use changing tools.
- **CON-14:** an approved tool request allows the tool (never through a model client); an approved connection request becomes a need listed with Add, holding nobody.

## Revision 2.27 (23 Nov 2026): connections, part 7B.4

- **CON-15, IF-5.6:** adding any MCP server and allowing any tool are human-only, not only command servers and changing tools: a model client could otherwise give agents new reach. Testing a server with a value and choosing where a secret is sent are human-only too.
- **7.18:** the MCP server table lists the states that may be deleted, so it can be checked.
- **IF-5.1:** crewmind's own MCP tools carry the read-only and destructive annotations from the catalog's reversibility, so any client, crewmind's own connections included, can tell readers from writers.
- **CON-10:** a sign-in expires after ten minutes; tokens are refreshed a minute before expiry; a server waiting for sign-in meets no need, so its seats are held.

## Revision 2.26 (23 Nov 2026): connections, part 7B.3

- **CON-6, EXE-14:** only a run with a secret sent for it goes through the egress proxy, so the proxy never stands in the way of ordinary traffic; the proxy connects only to public addresses (WRK-12) and says why it refuses; a secret is never added to plain HTTP; upgrades to a site with a secret are refused; the authority is valid for ten years and certificate validity follows the wall clock; idle connections close after `proxy.idle_timeout`.
- **Appendix A:** `proxy.idle_timeout` (5 min, 10 s–1 h, install) and `CREWMIND_EGRESS_PORT` (a free port by default).

## Revision 2.25 (23 Nov 2026): connections, part 7B.2

- **CON-7, CON-3:** given secrets and variables reach the harness over the run's own channel when the run starts and only the commands it runs receive them, never a container's settings; file secrets are in `CREWMIND_SECRETS_DIR`, removed when the run ends.
- **CON-4:** replacing or changing a granted connection also ends the seat's warm chat process.
- **CON-8:** the ingress points are named: every agent API call and model request, before anything reads them, and the workspace snapshot.

## Revision 2.24 (23 Nov 2026): connections, part 7B.1

- **CON-1:** connection names: a letter first, then letters, digits, `_`, `-` and `.`; unique per owner whatever their case; a need is met by a same-kind connection whose name matches whatever its case.
- **CON-2:** a value larger than `secret.max_size` is refused; the expiry date is a UTC day and the secret expires the day after; the `.env` review shows names, kinds and problems, never values, and secrets added from a `.env` are given to the agent under their own name.
- **Appendix A:** `secret.max_size` (64 KB, 1 KB–1 MB, install).
- **IF-3.1:** a read whose input holds a secret is sent as a POST body, like one that takes a document; a secret never travels in a URL.
- **CON-15:** each project's Connections is a panel under More, opened from the start dialog and from anything missing, rather than a top-level tab.

## Revision 2.23 (23 Nov 2026): connections, phase 7.B

- **CON-1 to CON-16 (new section 6.17):** secrets, variables and MCP servers: three scopes (install, person, project), attachment and role grants, write-only values, secrets sent for the agent by the egress proxy as the default, secrets given to the agent with masking, remote and command MCP servers with no auth, bearer, custom header and OAuth, needs and starting without them, the Founder and the crew knowing what a project has, the screens, records and errors. Role secrets were specified only as "injected" (EXE-13) and never built (phase 7.B plan, owner, 23 Nov 2026).
- **INT-4:** renamed "MCP servers (data sources)"; how servers are added and reached moves to CON-9 to CON-13; the permission rules stay.
- **EXE-13, EXE-14:** point to CON; the egress proxy blocks and reads nothing except connections to sites with a secret sent for the run.
- **PRJ-1, FND-13, IF-4.7:** open needs are prompted for, and block the start unless the chairman starts without them, holding the dependent seats.
- **INV-6:** the exception is secrets given to the agent, masked everywhere agent text is stored or sent to a model.
- **IF-5.6:** OAuth sign-in to an MCP server, adding a command server and deleting a connection are human-only.
- **7.18:** state tables for the connection, the MCP server and the need.
- **Appendix A:** ten settings for secrets, MCP servers and the proxy.

## Revision 2.22 (23 Nov 2026): agents have names

- **EXE-18 (new):** every agent has a person-like name it is shown by ("Maya, the CEO"), given at hire or drawn from a fixed pool, unique in the project; the chairman renames one with `roster.rename_seat` (every surface, recorded); `@Maya` addresses it; its prompt and context pack name it. The seat name stays the identity, including the stored author of chat messages.
- **EXE-15:** "who it is" includes the agent's name.

## Revision 2.22 (23 Nov 2026): agents run on a one-CPU host

- **EXE-12, WRK-7:** a container's CPU limit is what was asked for, or every CPU the host has when it has fewer. On a one-CPU server every run was refused, because the default asks for two.

## Revision 2.21 (23 Nov 2026): your own name

- **ACC-8 (new):** a person sets their own display name (`auth.set_name`, every surface); the change is recorded. The web showed the seeded "Admin" with no way to change it. Confirm: Q-021.

## Revision 2.21 (23 Nov 2026): a draft can be discarded

- **7.19, FND-1:** a drafting conversation gains the state discarded. The person who started it may discard it; it leaves their list of unfinished drafts and no project comes of it (owner, 23 Nov 2026).

## Revision 2.20 (22 Nov 2026): one count of what waits on you

- **HUM-10, CHAT-18:** open action cards are on the desk, and the project header's "waiting on you" is the caller's desk for that project, snoozes included. The header used to count open action cards only, so it said "nothing" while proposed scope waited on the desk. Confirm the action-card addition: Q-020.
- **No requirement text changed for the web app redesign** (docs/design/): it is a new arrangement of the same operations.

## Revision 2.20 (23 Nov 2026): the Founder asks a round at a time

- **FND-4, Appendix A:** `grill.pace` defaults to batch. A first real drafting on a slow reasoning model took 45 minutes at one decision per turn. The thirteen decisions now take three rounds. A round is answered as a whole before the Founder's next turn, and an unchanged goal keeps its grade (owner, 23 Nov 2026).
- **FND-2, FND-11:** `propose_spec` takes `changes` once a draft exists, so the Founder sends only what differs, and every draft is rehearsed as it is kept. The Founder is shown its own draft and the role list at the start of each turn. Measured on a real model with the same brief: the full interview went from over 45 minutes to about 3.5.
- **WRK-5, WRK-8:** when a check fails and the work is in a pinned test file, the output says so and the CEO is told at once. A real crew lost two tasks to this: the CEO had pinned the file the worker was to write.

## Revision 2.19 (22 Nov 2026): container mode proven on a real Docker host

- **EXE-12:** a sandbox container runs as an unprivileged user with no capabilities: the server's own user, or user 10001 of the agent image when the server runs as root. The fixed number is stated here because it must match the image.
- **EXE-12:** a server that is itself a container joins each project's network, and an idle project's network is removed. Docker has room for about 30 networks by default, so one network kept per project would stop new projects from running.
- **NFR-2, NFR-3, NFR-4:** for a full server these are the shell scripts in `deploy/`, which call the server's own setup, backup and restore (ADR-0009). No requirement text changed.
- **Open:** a slim install on a Linux host cannot yet run agents in containers, because a container cannot reach a server bound to 127.0.0.1 (Q-019).

## Revision 2.18 (22 Nov 2026): phase 7 plan answers

- **FND-2:** Founder calls are metered against an install-level account and count against no project budget (R-31).
- **FND-12:** one quick-mode target, under 2 minutes (R-32).
- **RHS-1:** rehearsal always runs on a fresh in-memory SQLite database; the code refuses any other (R-51).
- **LIB-1:** a role states its seat kind (ceo, worker or reviewer); "can be the CEO" is the kind ceo. A role has a slug, and no two roles share a name. Web is a permission; a role that cannot run without web search says so separately.
- **LIB-3:** anyone adds a role or a crew; only an admin changes one that exists, because every later project picks the change up. A shipped role whose text changes becomes its next version.
- **LIB-2:** a crew's estimate may be empty; a team's first named member leads it.
- **LIB-4:** the spec's fields are named; a spec with a problem creates nothing; a spec that carries a value where a credential name belongs is refused; what a spec asks for that the install lacks is listed as missing, not refused. A spec embeds only custom roles.
- **PRJ-9:** a clone is an export imported under a new name by the same chairman.
- **WRK-12:** domains a spec declares as controlled count as the project's own.
- **IF-3.1:** a read that takes a whole document is sent as a POST body.
- **RHS-1:** the drill's database is a fresh file in a folder of its own, not in memory: SQLite in memory cannot serve the dispatcher, the runner and the jobs at once. The drill is its own process, with a time limit (`rehearsal.max_seconds`), a crew in code, and one agent at a time.
- **RHS-2, RHS-3:** where the walk ends for each project type; estimates are to the first close.
- **EXE-5:** runs queued at the same instant are leased in the order their seats were created.
- **Appendix A:** `rehearsal.max_seconds`.
- **FND-1:** where the conversation is kept before the project exists; a document is attached as text; refused tool calls are kept.
- **FND-4:** who pays is looked up when there is one credential or none.
- **FND-5:** what "ready" means; creating is confirming; an assumption never replaces words or an answer.
- **FND-7:** what the platform checks in a grade; the verdict is computed.
- **FND-8:** a goal with a date in its prose is refused.
- **FND-12:** a quick draft is rehearsed; create and start are one step.
- **FND-15:** what a long paste is; items quote the document; examples reach the CEO labelled.
- **LLM-14, Appendix A:** `founder.credential`, `founder.model_class`, `grill.min_characters`.
- **IF-1.2:** an operation called from inside another runs its own preparation step.
- **FND-16:** one grilling at a time; what the CEO may not do while it is open; a conflict names what it conflicts with.
- **PRJ-7:** promote opens a Founder drafting with the findings report as its document; the Deliver project exists once that draft is confirmed.
- **IF-5.8:** the design doctrine and the goal grammar are served as documents; the design prompt goes through the Founder.
- **FND-14:** the finding is shown in the project's status, with its fix.
- **IF-4.6, IF-4.7:** `crewmind draft` is the terminal's drafting command; `crewmind founder eval` compares the grader with hand grades.

## Revision 2.17 (22 Nov 2026): phase 6 plan answers

- **HUM-5:** a question's default stays within the CEO's authority and may not spend, grant or widen scope (R-27).
- **HUM-6:** each flag kind is marked state or event (R-47).
- **IF-5.6, IF-5.2:** approving a skill version is human-only; reopen, complete and edit memory join the steer scope (R-33).
- **INV-22:** only time-based wakes are compared (R-48).
- **HUM-8:** how a mistake's cost is computed.
- **HUM-9:** what a lever does; green also means no open flag.
- **HUM-10:** what is not on the desk.
- **HUM-11:** how the brief is delivered before mail exists.
- **INV-24:** a chat run that gives no reply is answered by a platform status, not run again.
- **GOV-8:** purchases are declared until a purchasing integration exists.
- **IF-5.2:** one table maps each operation to its scope; the person's own account and instance administration are reached by no client.
- **IF-5.1, NFR-13:** each OAuth step is an operation behind the standard endpoint; a code presented with wrong values is spent; redirects are http on this machine until an admin allowlist exists.
- **IF-5.8:** the output standard is served as a document; the Founder doctrine and goal grammar join with the Founder.
- **INT-6, INT-7:** the install's outbound mail account moves to phase 8 with project mailboxes; until then alerts and briefs go by browser push and in the app (owner).

## Revision 2.16 (22 Nov 2026): phase 5 build

- **PLN-1:** a CEO proposal carries an estimate; the CEO gives the first estimate of a chairman-authored requirement that has none.
- **PLN-12:** the two conditions the platform can check, what "holds work" means, and that a condition fires once.
- **GOV-5:** what "the projection fits" means for a raise; one waiting request of each kind.
- **GOV-10:** which draws count as the one draw.
- **WRK-11:** when a filed gap review stays current; a waived gap's requirement leaves scope; what happens with no independent reviewer.
- **PLN-9:** a short gap is worded in hours.
- **PLN-1:** a CEO reopening scope meets the same limits as a CEO proposing it; an Explore project takes no requirements.
- **PLN-10:** a reviewer that did work under a requirement does not rule on it.
- **BG-2:** writes and job passes wake waiting jobs at once inside one server process.
- **SPD-8:** how each stretch of time is attributed.
- **SPD-9:** which seats count as idle, and what "closed" means.
- **PRJ-8:** completed, missed and skipped stated in full; when a cycle closes and when the next opens.
- **PLN-11:** the pattern has one group; losing ground needs a full window and is announced once.
- **PRJ-7:** how a bet's kill date is set; a confirmed finding cites verified evidence; what promote does before the Founder exists.

## Revision 2.15 (22 Nov 2026): phase 5 plan answers

- **GOV-3:** in wrap-up mode a new task may also serve a bet already active (R-24).
- **GOV-10:** what an Explore draw allows afterwards; a Deliver draw is refused when plan tokens are unknown (R-46).
- **PLN-10:** what "work has changed" means (R-40); a metric requirement is met when a reading reaches its target (R-44).
- **PLN-11:** until connectors exist, a metric is read from a public URL with a pattern, through the SSRF guard.
- **PRJ-8, 7.1:** skipped and missed cycles defined (R-45); the chairman can complete an Operate project (R-62).
- **INV-18:** reworded so a met requirement with done tasks does not break it (R-55).
- **7.1:** a CEO adds scope to a ready project only through a chairman directive (R-61). R-58 was already in 7.6.
- **PLAN.md, traceability.csv:** SPD-5 moves to phase 6, with question items.

## Revision 2.14 (22 Nov 2026): owner answers after phase 4

- **WRK-16, 7.16:** the declaring agent may finish a side effect in any later run, and the chairman may close a declared one as outcome unknown, so none is stranded (Q-011).
- **PLAN.md, traceability.csv:** WRK-10 moves to phase 6, with decision items (Q-010).

## Revision 2.13 (22 Nov 2026): solo projects

- **Section 3, WRK-9:** solo is a working shape. With independent read off a solo project is one agent: the platform's reviewer seat is stood down and comes back when independent read is turned on again. A task closes unread only when the one reviewer did the work (Q-009, owner: "solo has to work").

## Revision 2.12 (22 Nov 2026): phase 4 build

- **Section 3:** a CEO with only a reviewer seat is solo; a lead or worker seat ends that (Q-009).
- **WRK-2:** the CEO names the team of a top-level task; in a solo project the CEO claims.
- **WRK-4:** what "one item" is, and where the claim-expiry time is counted from.
- **WRK-7:** the check runs in a copy of the workspace; 4,000 characters of output are kept.
- **WRK-9:** the platform staffs a reviewer seat when a project with independent read has none; how the reviewer is chosen (Q-009).
- **WRK-12:** which failures are final, what a controlled domain is, and how the quote is matched.
- **WRK-14:** killing a task kills its open subtasks.
- **WRK-17:** what a URL watch checks; browser-script watches arrive with the agent browser.
- **EXE-16, GOV-7:** when the stall alarm repeats, and what counts as a change of work state.

## Revision 2.11 (22 Nov 2026): phase 4 plan answers

- **WRK-3:** "the same command test" means the same pinned command and test-file hashes (R-41).
- **WRK-5:** can't-fail commands are a fixed list (R-42).
- **WRK-12:** evidence is fetched after the task was created and must contain the claimed content; event times are compared only where the source supplies one (R-43).
- **WRK-8, 7.3:** a failed check or rejected review returns the task to ready, reserved for its previous claimant (R-54).
- **PLAN.md, traceability.csv:** the final gap review (WRK-11) and its exit-demo line move to phase 5, where requirements exist.

## Revision 2.10 (21 Nov 2026): owner answers after phase 3

- **NFR-23:** idle memory under 400 MB applies before recall memory is first used; about 450 MB once it is in use (Q-008).
- **PLAN.md:** the phase 2 exit demo no longer includes a run on a real provider; no real-provider test is kept (Q-006).
- **MSG-5:** the interim meaning of reopen evidence is agreed as built (Q-007).

## Revision 2.9 (21 Nov 2026): phase 3 plan answers

- **MEM-1:** pinned memory lives in the project database, not only Postgres (R-26). A chairman's write is never refused by a size cap; it opens a flag instead. Agent writes are refused at the cap, and a cap cannot be lowered below current use (R-28).
- **MEM-2:**
  - On SQLite the vector store is Qdrant in embedded mode (Q-001).
  - Mem0 keeps its own history file in the data directory; it is backed up and purged with the data.
  - Mem0's telemetry is off, and the library loads on first use.
  - The embedding model is an ONNX model shipped inside the package and the image (R-52).
- **MSG-4:** a pinned message that fits is proposed in the chairman's words; only a longer one is shortened by a model (R-49).
- **MSG-3:** a directive that changes a chairman-only setting becomes an action card the chairman confirms (R-23).
- **MSG-7:** the example-figure check is a mechanical lint (R-50).
- **MEM-2:** the model is never fetched at run time; pgvector needs a superuser to enable it and is left out of restores.
- **MEM-3:** names the scopes an agent reads; a chat run writes only its own.
- **MEM-4:** where extraction runs, where facts go, and when they are untrusted.
- **MEM-6:** what pinning an entry does.
- **MSG-11:** what counts as an involuntary restart; a sandbox may keep a warm process.
- **Appendix A (operational):** adds `CREWMIND_MEMORY_ENGINE` (MEM-2).
- **MSG-12:** names the three parts the lint measures.
- **MSG-7:** defines a figure and says the flag is feedback.
- **MSG-8:** slots are evenly spaced from the chairman's `brief.time` in the project's time zone (R-66).
- **CHAT-11:** the platform adds the quoted question after a `/fix` if the agent omits it.
- **MEM-1:** pinned sizes are estimated at 4 characters per token.
- **MSG-5:** until evidence records exist, reopen evidence is a newer file version or person's message; the ruling stands until the chairman approves (Q-007).
- **PLAN.md, traceability.csv:** the rest of MSG-11 (warm chat sessions) and the extractor part of LLM-14 are taken into phase 3.

## Revision 2.8 (21 Nov 2026): owner answers after phase 2

- **LLM-12:** a provider ceiling is set per provider by an admin; there is no default and no registry setting (Q-004).
- **PLAN.md, traceability.csv:** the spinning guard of GOV-7 and the stall watchdog EXE-16 move to phase 4, where tasks exist (Q-005).

## Revision 2.7 (21 Nov 2026): phase 2 build

- **CHAT-20:** push subscriptions are accepted only for browser push services over https; the install signs pushes with one key pair whose private half is a secret; alarms are queued then sent once per browser and held up to 24 hours; platform pauses are alarms, the chairman's own hold is not.
- **CHAT-4:** a stopped reply is marked in the chat and does not start again by itself.
- **CHAT-9:** an upload's chat line starts no reply and costs no tokens.
- **MSG-1:** a chat reply over the length limit is posted cut, with a note.
- **IF-3.5:** chat history with no cursor returns the newest messages and pages back.
- **Appendix A (operational):** adds `CREWMIND_AGENT_API_URL` (IF-6.1, EXE-12) and `CREWMIND_MOCK_SCRIPT_DIR` (LLM-8).

## Revision 2.6 (21 Nov 2026): phase 2 plan answers

- **MSG-11:** a chat session holds many chat runs, one per reply; the session is not a run (review R-35).
- **EXE-8:** each retry is a new run linked to the same wake (R-36).
- **INV-13:** nothing new is leased at or above `run.concurrency`; lowering it kills no live run (R-37).
- **ART-5:** locked files are mounted read-only into sandboxes (R-38).
- **ART-6:** at the storage quota, publishing is refused and snapshots are skipped, with a flag (R-39).
- **NFR-20:** each phase plan lists its warn-only rules; a rule an invariant cites always enforces (R-29).
- **INT-8:** the Brave Search API is the first search service.
- **Section 13:**
  - The build order now matches PLAN.md and ADR-0007 (R-25).
  - The multi-provider acceptance item tests API-key providers in v2.0; a subscription credential joins it in phase 8.
- **ACC-7, section 14:** second factor is after v2.0, in phase 8.
- **PLAN.md, traceability.csv:**
  - INV-10 moves to phase 6; INV-14 and INV-16 to phase 4; MSG-3 into phase 2.
  - Subscription logins and the vendor agent SDK harness (parts of LLM-2 and LLM-8) move to phase 8.

## Revision 2.5 (21 Nov 2026): phase 1 build

- **7.8:** the first admin is created in the invited state with a setup link, like any invite, not directly as active. This matches NFR-2 ("creates the first admin and prints a setup link").
- **7.11:** in a break-glass hand-on, a person who is not yet a member joins as a co-chair first, so an admin can replace a chairman who was the project's only member.

## Revision 2.4 (21 Nov 2026): phase 1 plan answers

- **ACC-5, 7.8:** deactivating a person who chairs a project is refused, naming the projects. An admin hands each chair on first.
- **PLAN.md, traceability.csv:** INV-4 and BG-2 move to phase 2, where runs and the dispatcher exist.

## Revision 2.3 (21 Nov 2026): phase 0 bootstrap

- **IF-1.3:** an operation belongs on the `slash` surface only when it declares a slash command, and a host-local operation belongs on `cli` only. This matches IF-1.1 ("its chat slash command, if any") and IF-4.2.

## Revision 2.2 (21 Nov 2026): plain, short output from every model call

- **P18, LLM-15 (new), MSG-12, Appendix A:**
  - Every model call the platform makes or prepares carries one output standard: plain English, the answer first, no padding.
  - Length is spent only where the task asks for it.
  - A test fails if any prompt-building path omits the standard.
  - Agent-to-agent messages and notes get a length budget, `agent.message_words` \[150\].
  - Measured and fed back, never refused (P1). LLM-15 is in phase 2.

## Revision 2.1 (21 Nov 2026): phase 0 spec review answers

Owner answers to the blocking items in `docs/spec-review.md`.

- **P5, WRK-6, INV-3, 7.3:** a solo project with independent read off may self-report observable-test tasks only. The exemption is now written into P5; command tests always need the platform check (R-01).
- **GOV-3, PRJ-2, EXE-9, 7.7, 9.2, section 13:** at the budget wall, in-flight runs finish within `run.max_tokens` and nothing new is leased. A hold, a kill, the refusal cap and every other pause still revoke at once (R-02).
- **7.1, PRJ-2:** projects carry a set of hold reasons (`chairman`, `budget_wall`, `auth_failures`, `skipped_cycles`), each lifted by its own trigger. `/resume` is refused while the wall holds (R-03).
- **Section 3, section 7, ACC-5:**
  - "Chairman" in a Who column means the chairman or a co-chair, except for delete and hand-on.
  - Instance roles are `admin` and `member`; any active person may create a project and becomes its chairman.
  - On hand-over, the previous chairman becomes a co-chair (R-04).
- **NFR-10:** current state lives in tables. Each change writes its event in the same transaction. Reports come from the log or from rebuildable read models, and frozen snapshots are events (R-05).
- **IF-1.2, IF-1.3:** `agent_api` is a catalog surface. Operations declare their principals, and surfaces not yet built are exempt as a whole, with their phase named (R-06).
- **IF-4.2:** install, `up`, update and `migrate --to postgres` join the host-local commands (R-07).
- **Section 7:**
  - New tables cover accounts, single-use links, sessions and tokens, MCP confirm tokens, membership, teams and seats, cycles, artifact locks, evidence, side effects and watches, directives, action cards, standing orders, closed decisions, corrections, threads, chat sessions, suggestions and notices, model credentials, circuit breakers, tool permissions, mailboxes, drafting conversations and skill versions.
  - New rows: platform defaults for proposed scope and commitments, cycle-roll reopening, platform blocking and killing of tasks, the chairman moving a commitment date, leased runs that never start, and flag, heads-up and mistake-report states.
  - A lifecycle missing from section 7 must not be implemented.
  - New interpretations to confirm in the phase plans: a seat is paused when its seat check fails; the artifact status label is derived on read, not stored (R-08).
- **7.1, EXE-5:** a matrix states which run kinds may lease in each project state (R-09).
- **GOV-1, Appendix A, section 3, ACC-3, PRJ-8, HUM-11, GOV-2:**
  - New settings: `authority.preset` (with `custom`) and the six `authority.*` verb settings; `project.timezone` and `person.timezone`; `cycle.period`, `cycle.roll_day` (0 = Monday) and `cycle.due_time`; `token.default_expiry`.
  - GOV-1 rules now differ by scope.
  - Appendix A gains a Constraints list and an Operational settings table. The port, data directory and sandbox ranges there are starting defaults (R-10).
- **PLAN.md, traceability.csv:**
  - PRJ-9, IF-4.6 and IF-4.7 move to phase 7.
  - Phase 1 takes minted MCP bearer tokens and the `read` scope from IF-5.1 and IF-5.2.
  - PRJ-1, PRJ-2, PRJ-3, PRJ-10, NFR-2 and NFR-5 are built as extension points (R-11).

## Revision 2 (21 Nov 2026)

- **Renamed** the project from yaaf to crewmind: product, package, CLI, environment variables, Slack and mail prefixes (ADR-0008).
- **Full rewrite from revision 1:** chat-first front door (CHAT); token-only budgets with the budget as the wall and a CEO reserve (GOV-2, GOV-3, GOV-10); speed requirements (SPD); one quality dial (LLM-3); mailbox per project, managed (Stalwart) or manual, with per-agent accounts (INT-6, INT-10); Mem0 recall memory with an exact pinned layer (MEM); every file an artifact (ART); grilling (FND-15, FND-16); Agent Skills (LIB-6); agent browser (EXE-17); A2A (INT-11); OpenTelemetry export (NFR-22); slim mode on SQLite (NFR-23); Python stack (NFR-24); state machines (section 7); settings registry (Appendix A).
- **Owner decisions recorded:** Python; Postgres and SQLite; budgets count non-cached tokens only; Mem0; separate mailbox accounts per agent; subscription logins are the user's choice. See `docs/decisions/`.
- **Removed:** tempo and bar presets, stakes, dollar model budgets, run-count allowances and inbox lanes, the global plan gate, measurement windows, the change stamp, directives inferred from chat, the budget overage multiple.
