# Phase 2 plan: chat and execution

Goal (PLAN.md): talk to a CEO in the chat. It runs real work in a sandbox through the model gateway, metered in tokens, and stops at the wall.

**Exit demo.**

- In the web app and in `crewmind chat`, the chairman talks to a CEO on the mock harness and on one real provider.
- An upload becomes an artifact.
- A run is metered by token kind, and only non-cached tokens count.
- Hitting the wall pauses the project.
- Killing a runner mid-run violates no execution invariant.

Status: **agreed with the owner on 21 Nov 2026.** The answers are at the end.

## Size, and a proposed split

Phase 2 carries about 95 requirement ids: more than phases 0 and 1 together, plus the first web code and the first terminal UI. I propose four parts, each ending with the suite green on both databases and its own small demo.

| Part | Builds | Demo |
| --- | --- | --- |
| **2a Execution core** | Roles (minimal), roster, runs, wake triggers, dispatcher, leasing, heartbeats, reaping, retries, sandboxes, the agent API (context, messages, notes, team), the ledger, the budget wall, runaway guards. Mock harness and mock provider only | A scripted CEO wakes on a message, runs in a sandbox, is metered, and the project pauses at the wall. Killing the runner mid-run breaks no invariant |
| **2b Models** | Model gateway on LiteLLM, model credentials, lineups, the quality dial, seat check, effort, circuit breaker, provider ceilings, health checks, web search, the vendor-neutral harness loop, the output standard (LLM-15) | The same run on one real provider, through the gateway, with no key in the sandbox |
| **2c Conversation** | Channels, messages, threads, chat runs and warm sessions, never-silent statuses, slash commands, action cards and directives, artifacts, uploads, workspace snapshots, the live event stream, `crewmind chat` in the terminal | The chairman chats with the CEO in the terminal, streaming; an upload becomes an artifact |
| **2d Web app** | `web/`: the chat, composer, header, activity feed, artifact previews, sign-in and setup-link pages. API client generated from the OpenAPI schema | The exit demo in a browser |

## Modules

```
src/crewmind/
  domain/execution/     roles, teams, seats; runs and their lifecycle; wake triggers; dispatcher;
                        leasing; liveness; retries; context pack (EXE-1 to EXE-11, EXE-15, EXE-16)
  domain/budget/        ledger, token budget, thresholds, the wall, runaway guards (GOV-2, 3, 6, 7, 9)
  domain/conversation/  channels, messages, threads, read positions, notices, chat sessions,
                        directives, action cards, pair breaker (MSG-1, 2, 9, 10, 11, 13; CHAT)
  domain/artifacts/     artifacts, versions, content-addressed storage, locks, quota (ART-1 to ART-9)
  gateway/              provider registry (data), LiteLLM calls, usage normalisation, metering,
                        per-run cap, credentials resolver, lineups, breaker, ceilings, health, search
  runner/               runner supervisor, sandbox interface, container and unisolated modes,
                        harness loop (vendor-neutral), mock harness
  surfaces/agent_api/   the agent API over HTTP and as MCP tools inside the sandbox (IF-6.1 to 6.3)
  surfaces/api/stream.py  server-sent events (IF-3.6); resumable uploads (IF-3.9)
  surfaces/cli/chat/    `crewmind chat` in Textual (IF-4.8)
web/                    the React app
content/output-standard.md   the one copy of the output standard (LLM-15)
```

## Tables

| Table | Holds |
| --- | --- |
| `roles`, `teams`, `seats` | A minimal role (name, kind, tools, credential names, charter, `min_class`, vision), teams pinned to a role version, seats with state (7.12) |
| `model_credentials`, `lineups` | Named credentials (value in `secrets`), kind, provider, state and breaker state (7.18); class-to-model lineup per credential |
| `runs`, `run_wakes` | Runs with kind, state (7.7), pinned model, effort, provider, credential, harness and caps (EXE-6); wake reasons per run (EXE-4) |
| `ledger_lines` | One line per model call: tokens by kind, run, seat, credential; counts for searches (LLM-9, INT-8) |
| `channels`, `messages`, `read_positions` | The one conversation model (MSG-13); threads by parent message |
| `notices`, `chat_sessions` | Notices consumed on read; warm sessions (7.17) |
| `directives`, `action_cards` | 7.17 |
| `artifacts`, `artifact_versions` | Name, kind, audience, lock; versions with content hash and author. Bytes live in a content-addressed directory under the data directory (ART-2) |
| `uploads_in_progress` | Resumable upload state (IF-3.9) |

## Rules and their attack tests (the main ones)

| Rule | Attack |
| --- | --- |
| P3, INV-4 run tokens | A run token used for another run, another project, after the run ends, after a hold, after the refusal cap, on the human API: all refused |
| INV-6 no keys in sandboxes | A scripted agent dumps its environment, files and every agent API answer: no provider key, and no secret outside the role's named credentials |
| INV-8, P9 every token metered | Kill, fail and reap runs mid-call: every call the gateway accepted has a ledger line |
| INV-9, GOV-3 the wall | Race many runs at the wall: spend exceeds it by no more than the in-flight runs; nothing new leases; `/resume` refused |
| GOV-6 per-run cap | A run that keeps calling past `run.max_tokens` is refused at the gateway, across retries |
| INV-11, P8 idle costs nothing | A project with no trigger and no message makes no model call over many dispatcher ticks |
| INV-12, INV-13, INV-15 leasing | Two runners racing for one run; a reaped worker reporting late; concurrency lowered while runs are live |
| EXE-10 refusal cap | Five refusals revoke the token; rephrasing does not help |
| INV-20 held and paused | A held project leases no work run; chat still works; at the wall chat gets a status card |
| INV-24, CHAT-3 never silent | Provider down, budget at the wall, project held, crash mid-reply: a reply or a platform status within 60 seconds |
| MSG-2, MSG-9 who speaks | An agent posting in the project chat unaddressed; two agents looping in a thread |
| ART-5, ART-9 artifacts | An agent writing a locked artifact, or publishing a name with a path |
| LLM-6 seat check | A seat with no paying credential fails before any sandbox starts or token is spent |

Chaos tests kill runners, drop database connections and race runners against INV-8 to INV-15.

## Decisions this plan makes

| Topic | Choice |
| --- | --- |
| Live stream | Server-sent events (IF-3.6). Polling keeps working |
| Chat sessions and runs | One warm session holds many chat runs, one per reply; each run is metered and capped on its own (review R-35) |
| Retries | Each attempt is a new run linked to the same wake; a wake counts once (review R-36) |
| Lowered concurrency | Nothing new is leased while the count is at or above `run.concurrency`; live runs are not killed (review R-37) |
| Sandbox network | Open egress as EXE-14 specifies, stated in SECURITY.md. The stricter rule in review R-22 concerns the agent browser and is settled with it in phase 8 |
| Model classes | A data file maps known model families to frontier, balanced or fast. Lineups pick the newest reachable model per class daily; an admin can override (LLM-4). Unknown models are left unclassified, and shown |
| Usage normalisation | Per-provider tests from recorded responses for Anthropic, OpenAI and Gemini, covering cache writes and cache reads (ADR-0003) |
| Web stack | Vite, React, TypeScript; API types generated from the OpenAPI schema; Vitest and Playwright; built files served by the server |
| No tasks yet | Tasks belong to phase 4. In phase 2 the CEO wakes on messages, notices, the planning triggers that exist, and the heartbeat |

## Owner answers (21 Nov 2026)

| Question | Answer |
| --- | --- |
| Split and review | Built in the four parts above, in order, each with the suite green on both databases. **One review stop, at the full exit demo** |
| Sandboxes with no Docker daemon here | Both modes behind one interface. The unisolated development mode is built and fully tested here. Container mode is written against the Docker SDK; its tests skip without a daemon and must pass in CI or on the owner's machine. Until then it is reported as unverified |
| First real provider | Anthropic. The suite uses recorded responses; the live half of the exit demo needs an API key, requested through a secure form when part 2b is ready |
| Subscription logins and the vendor agent SDK harness | Both move to phase 8. Phase 2 ships API-key credentials, the mock harness and the vendor-neutral loop |
| Web search service | The Brave Search API first, behind a small interface |
| Id moves | INV-10 to phase 6; INV-14 and INV-16 to phase 4; MSG-3 into phase 2 |
| Review items R-25, R-29, R-35 to R-39, R-67 | Accepted as recommended; applied in spec revision 2.6 |
| Web app scope | **Everything in phase 2:** the core chat plus audio and video previews, the installable phone app with push alerts, the command palette, side-by-side version compare and full-text search |

Two notes on these answers:

- **Push alerts** need the alert rules of INT-7, which are phase 6. Phase 2 builds the installable app and the push channel, and sends the alarms that exist by then (paused, budget wall). The per-person alert levels and caps arrive in phase 6.
- **Warn-only rules** (NFR-20): none in phase 2. Every rule it adds guards authority, budget, secrets or execution invariants, so all enforce.

No open questions remain.

## Outcome (21 Nov 2026)

Phase 2 is built in its four parts. Of its 85 requirement ids, 61 are done, 20 are partial and 4 are not started; `docs/traceability.csv` has the tests and a note for each.

**Exit demo, item by item.**

| Item | Result |
| --- | --- |
| Talk to a CEO in the web app, on the mock harness | Done. 20 browser tests drive the built app on the real server, with the agent as a separate process |
| Talk to a CEO in `crewmind chat` | Done on the mock harness |
| The same on one real provider | **Dropped by the owner (Q-006).** No real-provider test is kept; real providers are covered by recorded responses. No real model has been called by the build |
| An upload becomes an artifact | Done, small and chunked uploads |
| A run is metered by token kind; only non-cached tokens count | Done |
| Hitting the wall pauses the project | Done, and sends a push alarm |
| Killing a runner mid-run violates no execution invariant | Done. This test also found a SQLite lock that outlived a cancelled task; fixed |

**Partial or not built.**

- **Container sandboxes (EXE-12):** proven on 22 Nov 2026 against Docker 29, after phase 7. The first real run found that the Docker SDK was not a dependency, the image did not exist, the search path hid the image's Python, a container could not reach the server, and a container had no user it could write the workspace as. All are fixed; `tests/acceptance/test_containers.py` covers them and skips without a daemon or the image. A slim install on a Linux host still cannot use container mode (Q-019).
- **Warm chat sessions (MSG-11):** each reply is its own run in a new process. Reusing a warm process, and the restart rules, are not built.
- **Spinning guard and stall watchdog (GOV-7, EXE-16):** need tasks. Asked to move to phase 4 (Q-005).
- **Model health (LLM-10):** the smoke call only. No capability check, no daily model-list upkeep.
- **LLM-13** (cost estimate, a MAY) and **LLM-14** (platform models for the Founder and memory): not built.
- **Agent API as MCP tools inside the sandbox (IF-6.1):** HTTP only.
- **Image description for seats without vision (CHAT-9):** not built.
- **Database notifications (BG-2, a SHOULD):** polling only.
- **Web app:** no channel switcher, no "waiting on you" panel, no spreadsheet preview; mentions complete agents and teams only; the chat opens at the newest 200 messages with no control to load earlier ones. PDF, audio and video previews use the browser's players and were not watched playing. Push alerts were never sent to a real push service. Accessibility was checked by automated scans, not by a person with a screen reader.
- **Push alarms** are tried once per browser and not retried.

**Found and fixed on the way.**

- `crewmind chat` did not open the terminal chat: the `chat` command group hid it.
- A reply longer than a message was refused and its run repeated.
- A reply stopped with Esc started again by itself.
- Every upload triggered a full reply.
- Every command spent 2.7 seconds loading the model library. Start-up is now about 1.3 seconds.
- On SQLite, a task cancelled mid-query kept the write lock for up to 30 seconds.

**Tests.** 240 Python tests on SQLite in about 55 seconds and 241 on Postgres in about 85 seconds, in parallel; 52 web unit tests; 20 browser tests in about a minute.
