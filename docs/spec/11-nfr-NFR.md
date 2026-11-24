## 11. Non-functional requirements

**Deployment and operations**

- **NFR-1** Self-hosted, open source, no telemetry to the vendor (OpenTelemetry export goes only to the admin's own collector, NFR-22), no vendor account. Two supported shapes: a full server (Postgres, containers, separate runners) and a slim install (SQLite, one process; NFR-23). Developers can run from source.
- **NFR-2** One idempotent install command for a server. It:
  - checks prerequisites;
  - creates the master key, and never overwrites one;
  - binds to localhost;
  - starts the services and migrates on start;
  - creates the first admin and prints a setup link;
  - loads the starter libraries;
  - offers guided Slack and email setup.

  The target is 10 minutes from a prepared server to a running project (section 1.3).
- **NFR-3** The update command refuses a dirty checkout, backs up first, updates, migrates and restarts. It has a dry-run mode.
- **NFR-4** Backup is one owner-readable archive holding the database, the master key and artifacts (workspaces optional). Restore saves the current state first. Destructive wipes require typing a confirmation word.
- **NFR-5** Health endpoints: liveness, and readiness (database reachable and schema current, otherwise 503). A `doctor` command checks the whole install, including Slack and email, and prints a fix for each finding. Each project has a health card with a fix per finding.
- **NFR-6** The server binds to 127.0.0.1 by default. Publishing it requires TLS and a configured public base URL. For hosted AI clients and Slack, only the MCP, OAuth and Slack event endpoints need to be public.
- **NFR-7** Configuration has two kinds. **Operational** settings are environment variables: database URL, master key, ports, sandbox mode and limits, public URL. **Governed** settings are per-project, in the database, changed only through the operation catalog with a reason (Appendix A). Model keys are never environment variables.

**Reliability and concurrency**

- **NFR-8** Two databases are supported: Postgres with pgvector for a full server, and SQLite for slim installs (NFR-23). Every test and every migration runs against both in CI, and domain logic never depends on one database's features except behind a storage adapter. On Postgres, leasing uses row-level skip-locking. All timestamps are timezone-aware and stored in UTC; local times use each project's timezone.
- **NFR-9** The dispatcher, scheduler, leasing, gateway and API all recover on their own after every pooled database connection drops.
- **NFR-10** Schema changes are forward-only migrations applied at start. State and history are kept as follows:
  - **Current state** lives in ordinary tables.
  - Every state change writes its typed event (actor, time, before and after) in the **same transaction** (INV-21).
  - **Reports and feeds** are derived from the append-only event log, directly or through read models. A read model can always be rebuilt from the log and is never edited by hand. A computed summary is never stored as the truth.
  - **Frozen snapshots** (receipts, scorecards, status-review numbers) are recorded as events: point-in-time records, never the current state.

**Security and privacy**

- **NFR-11** Every route declares its authorization, enforced before the handler runs and checked by a route-walking test.
- **NFR-12** Secrets are encrypted at rest under the master key. Tokens are stored as hashes only. Secret values never appear in logs.
- **NFR-13** The OAuth server for MCP enforces:
  - PKCE S256;
  - exact redirect matching against an allowlist (localhost by default; the setup wizard offers to add hosted AI clients the admin chooses);
  - single-use 60-second codes and 1-hour access tokens;
  - refresh-token rotation, with replay treated as theft;
  - audience binding;
  - a cap of 200 dynamically registered clients.
- **NFR-14** SECURITY.md states:
  - the trust boundaries;
  - what contains an agent run, and what does not (open network egress);
  - where the model gateway does not apply (subscription harnesses that need a local login, LLM-8);
  - the second-factor gap until it ships;
  - what skill scripts and the agent browser can reach; known sharp edges.

  This is a product requirement, not optional documentation.
- **NFR-15 Retention.**
  - Run traces and context packs are kept `retention.traces` \[90 days\], then reduced to their summary and token lines.
  - Workspace snapshots older than `retention.snapshots` \[30 days\] are thinned to one per day.
  - The event log, ledger, decisions and deliverables are kept for the life of the project.
  - Deleting a project purges everything (PRJ-10).

**Speed and cost**

- **NFR-16** Deciding whether an agent has work costs no tokens. Briefs, agendas, review snapshots, flags, watches, holds and rehearsals cost no tokens.
- **NFR-17 Latency targets:**
  - chat delivery acknowledged within 1 s;
  - first streamed words within 5 s at p50 and 15 s at p95 on a warm chat;
  - a platform status within 60 s whenever no reply has started;
  - a ready task leased within 10 s when limits allow;
  - app reads under 300 ms at p95 for a project with 100,000 events on modest hardware.

  MCP payloads respect the context budget (IF-5.7).

**Experience quality**

- **NFR-18** The app meets WCAG 2.2 AA:
  - full keyboard operation;
  - screen-reader labels on every control and card;
  - light and dark themes;
  - reduced-motion support;
  - responsive layouts from phone to wide desktop.

  All user-facing strings live in one catalog, ready for translation (English first). Every empty state says what will fill it and what to do next. Every error says what happened and the legitimate next step (IF-1.4).

**Quality and tests**

- **NFR-19 Test layers.**
  - Domain rules are pure functions or state machines (section 7) with fast unit tests. A thin layer of HTTP contract tests covers each operation. Attack tests cover every rule (P10). Chaos tests cover leasing, claims and side effects.
  - The default suite never calls a paid model. Behaviour is covered by scripted-harness scenarios whose expectations include **floors** (a CEO that does nothing while losing must fail) as well as ceilings.
  - The scenarios include the v1 frustrations as regression tests:
    - a standing order ignored;
    - an example used as data;
    - a closed decision re-argued;
    - a question answered sideways;
    - a delegated decision asked about;
    - chat acted on without a directive;
    - work after a hold;
    - a silent chat;
    - a fabricated figure;
    - an unwatched launch.
  - Optional paid judges grade planning quality, plain language and sycophancy comparatively. Golden scenarios assert behaviour, never exact prompt wording.
- **NFR-20** Every rule records how often it refuses and how often a refused call later succeeds, so false refusals are visible. Each phase plan lists which of its rules start in warn-only mode; a rule an invariant cites always enforces. New rules ship in warn-only mode first, unless they guard authority, budget, secrets or side effects.
- **NFR-21** Code uses the domain names in section 4. No metaphor identifiers, and no comments that narrate incidents.
- **NFR-22 OpenTelemetry export.** nightsquad emits OpenTelemetry traces and metrics, following the GenAI semantic conventions, so runs can be watched in tools people already use (Grafana, Langfuse, Datadog and others).
  - **Spans:** every run, model call, tool call, agent API call, browser action, check, watch, scheduled job and A2A exchange. W3C trace context is carried from dispatcher to runner, harness, gateway and agent API, and onward on outbound A2A calls.
  - **Metrics:** tokens by kind, seat and model; run outcomes; refusals by rule; queue wait; chat latency; budget used against the wall.
  - **Off by default, and never to the vendor.** Export goes over OTLP only to a collector the admin configures (`otel.endpoint`). NFR-1's "no telemetry" still holds: nothing is sent anywhere else.
  - **Content stays home unless chosen.** Prompts and outputs are left out of spans unless `otel.capture_content` \[off\] is on for a project. Secret values are never exported (INV-6).
  - nightsquad's own trace store stays the source of truth; the export is a copy.
- **NFR-23 Slim mode.** nightsquad can run small, for one person on a laptop or a small virtual machine.
  - **One process** runs the server, scheduler, gateway and one runner, on SQLite, with the bundled local embedding model and Mem0's embedded vector store.
  - **Nothing extra required:** no Postgres, no message broker, and no Slack, email, A2A or OpenTelemetry unless configured.
  - **Sandboxes:** containers when Docker is present; host-jail mode once it ships (phase 8).
  - **Install:** one command (for example `uv tool install nightsquad`, then `squad up --slim`).
  - **Targets:** start in under 5 seconds; idle memory under 400 MB before recall memory is first used, and about 450 MB once it is in use, because the memory library and its embedding model stay loaded.
  - **Same rules everywhere.** Slim mode runs the same rules, operations and tests as a full server; only storage and process layout differ.
  - **Moving up:** `squad migrate --to postgres` moves a slim install to a full server with no data loss.
- **NFR-24 Technology.** The rebuild is written in Python.
  - **MUST:** Python 3.12 or later for the server, runners, scheduler, model gateway, memory, harness loop, CLI and MCP server.
  - **SHOULD**, each deviation recorded with a reason:
    - FastAPI with Pydantic v2 for the HTTP API, with the operation catalog (IF-1.1) defined as Pydantic models, so the OpenAPI schema comes from it;
    - SQLAlchemy 2 with Alembic for both databases;
    - asyncio workers that lease from the database for background jobs, with no Redis or broker;
    - LiteLLM as a library inside the model gateway (LLM-1), and Mem0 as a library for recall memory (MEM-2);
    - the official MCP Python SDK; Typer for the CLI; Textual for `squad chat`;
    - the Docker SDK for Python for sandboxes; Playwright for Python for the agent browser (EXE-17);
    - the OpenTelemetry Python SDK (NFR-22);
    - uv, ruff, strict type checking, and pytest with Hypothesis for the state machines.
  - **The one exception is the web app:** TypeScript with React. A streaming chat at the bar set in section 5 needs it. Its API client is generated from the OpenAPI schema, so it holds no business rules (IF-1.2).
