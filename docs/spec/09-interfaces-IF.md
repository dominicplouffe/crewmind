## 9. Interfaces: chat, API, CLI, MCP, Slack and agent API

crewmind must be fully operable from any of its surfaces. The HTTP API is the product's real interface. The app (chat and panels), the CLI, the MCP server and the Slack bridge are all clients of one shared set of operations. Anything a person can do in the app they MUST be able to do from the API and the CLI, and from MCP within the client's scope (exceptions in IF-5.6).

### 9.1 One operation catalog, many surfaces

- **IF-1.1** Every domain action is defined once as an operation:
  - a name;
  - input and output schemas;
  - the required authority (role or scope);
  - a reversibility class: `read`, `reversible` or `irreversible`;
  - the audit actor it records;
  - its chat slash command, if any.
- **IF-1.2** HTTP routes, CLI commands, MCP tools, slash commands, Slack actions and agent API tools are thin adapters generated from, or registered against, that catalog. No surface contains business rules of its own. The surfaces are `api`, `cli`, `mcp`, `slash`, `slack` and `agent_api`.
- **IF-1.3** A conformance test enumerates the catalog.
  - Each operation declares the principals it serves (section 9.2): person, MCP client, agent run. It belongs on every surface those principals reach: a person reaches `api`, `cli` and `slack`, plus `slash` when the operation declares a slash command (IF-1.1); an MCP client reaches `mcp`; an agent run reaches `agent_api`. A host-local operation (IF-4.2) belongs on `cli` only.
  - The test fails when an operation is missing from a surface it belongs on, unless the catalog carries a written exemption reason for that operation and surface.
  - A surface not yet built is exempt as a whole, with the phase that builds it named. Once that phase starts, the exemption is removed. The same test checks that every decision-item kind appears on every surface listed in HUM-1.
- **IF-1.4** Refusals are identical on every surface: the same machine code, the same rule id, the same plain sentence naming the rule and the legitimate path forward, and the arithmetic where numbers are involved (GOV-9).

### 9.2 Principals

| Principal | Credential | Reaches | Notes |
| --- | --- | --- | --- |
| Person | Password, then a browser session or a named, expiring, revocable personal token | App, human API, CLI | Rights come from instance role and per-project role |
| Slack user linked to a person | The install's Slack app, plus the person's linked Slack identity | The project's Slack channel | Acts as the person; recorded as "person via slack" |
| MCP client | Its own token or OAuth grant, never the person's credential | MCP server | Narrowed by scope; acts for one person; every write recorded as "person via mcp:\<client>" |
| Agent run | Per-run token: one run, one agent, one project | Agent API and model gateway only | Valid only while the run is live; revoked at end, kill, hold, a pause other than the budget wall (GOV-3), or the refusal cap |
| External system | Per-project signing secret | Webhook intake | Signature and replay window checked before anything is stored |

### 9.3 Human HTTP API

- **IF-3.1** JSON over HTTP, versioned (e.g. `/v1`), with a published OpenAPI schema generated from the operation catalog. Reads are GET requests, except a read that takes a whole document (checking a project spec), which is sent as a POST body.
- **IF-3.2** Every route declares who may call it, enforced before the handler runs. A test walks all routes and fails on any without a declaration.
- **IF-3.3** A project the caller cannot see answers exactly like a project that does not exist (404). A visible project with an insufficient role answers 403, naming the role required.
- **IF-3.4** A stable error envelope: `code`, `message`, `rule` (when a governed rule refused), `hint` (the legitimate path).
- **IF-3.5** Writes accept an idempotency key. Lists are cursor-paginated and filterable by time window. A chat's history, read with no cursor, is its newest messages, oldest of them first, with a cursor to page back.
- **IF-3.6** A live event stream (server-sent events or WebSocket) publishes project changes and streams chat replies token by token. Polling must still work.
- **IF-3.7** Browser sessions are protected against cross-origin writes. Signing out invalidates the session server-side, and a password change invalidates older sessions.
- **IF-3.8** Every read view the app shows MUST be a documented API read, so a third-party client could rebuild the app. That covers chat, overview, plan, board, org, runs and traces, evidence, deliverables and artifacts, memory, ledger, brief, agenda and record.
- **IF-3.9** Uploads use resumable multipart transfer up to `upload.max_size`.

### 9.4 CLI (`crewmind`)

- **IF-4.1** One command, `crewmind`, talking to the server over the HTTP API. It is configured by `CREWMIND_API` (the server address) and either `crewmind login` (stores a personal token) or `CREWMIND_TOKEN`.
- **IF-4.2** A small, explicitly marked set of host-local commands may touch storage directly, because they must work when the server is down:
  - install (NFR-2);
  - `up`, which starts the services and migrates on start (NFR-2, NFR-23);
  - update (NFR-3);
  - `migrate --to postgres` (NFR-23);
  - bootstrap the first admin, or issue a password-reset link;
  - backup and restore (NFR-4);
  - master-key rotation (ACC-6).

  Each is marked host-local in the catalog and exempt from the `api`, `mcp`, `slash` and `slack` surfaces. Nothing else may bypass the API.
- **IF-4.3** Every command supports `--help` and `--json`. With `--json`, or with no TTY: never prompt, write only data to stdout and diagnostics to stderr.
- **IF-4.4** Exit codes distinguish success, refusal by a rule, authentication failure, not found, and server unreachable.
- **IF-4.5** Secrets are read from a hidden prompt, stdin or a file. They are never echoed and never required as a command-line argument.
- **IF-4.6** Drafting a project in the terminal follows the Founder rules (FND-3):
  - each question arrives with a recommended answer;
  - Enter accepts it, a letter picks another option, and free text answers in the user's own words;
  - who pays is never pre-selected;
  - the conversation lives on the server, so it can be resumed elsewhere.
- **IF-4.7** After creating a project, the CLI asks for any missing model credential and each open need of the roster: secrets by hidden input, variables, and MCP servers by address (skippable; CON-5). It then prints the remaining setup checklist with links, and offers to start the project only when nothing blocks it.
- **IF-4.8** `crewmind chat [project]` opens a full-screen terminal chat with the same capabilities as the app chat:
  - streaming replies;
  - slash commands and `@` mentions;
  - file attachment by path or drag-and-drop where the terminal allows;
  - Esc to interrupt;
  - the Now / Next / Waiting-on-you header.

Required command groups (names are suggestions; coverage is required):

| Group | Must cover |
| --- | --- |
| Install and run | Guided setup, start all services, health check with fixes (`doctor`), update, backup, restore, rotate master key, open the app |
| Sign in | Login, logout, whoami |
| Chat | `crewmind chat`; send a message or a slash command non-interactively; upload a file |
| Projects | Create by conversation, `--quick`, `--from-file`; rehearse a spec; list; status; start, hold, resume, stop, reopen, complete, delete; set budget and quality; amend a setting; export and clone |
| What needs you | An interactive one-item-at-a-time desk; the daily brief across projects; decide items; acknowledge flags; extend a bet; unfreeze a thread; audit samples |
| Look inside | Overview, agenda, plan, board, org, activity, runs and a run's trace, channels and tail, deliverables and artifacts, memory, evidence, full project snapshot as JSON |
| Budget | Token use by project, seat, model and day; receipts; ledger lines; real-world spend |
| Models and keys | Add, edit, hide and delete model credentials; subscription usage; smoke-test a key; check a provider; view and override lineups; provider ceilings; web search service; platform model settings |
| People | Invite a user (prints a one-time setup link), list, promote or demote, deactivate or reactivate; project members add, change role, remove; hand on the chair; link a Slack identity |
| MCP clients | Mint a token with scopes, list, revoke |
| Integrations | Connect Slack (install) and pick a project's channel; connect mail servers and outbound mail (install); give a project a managed or manual mailbox; manage agent addresses and the email allowlist; store project secrets; webhooks; data sources; A2A endpoints; OpenTelemetry export |
| Libraries | Load and export roles and crews; add, review and approve skills |
| Ambient | A one-line status-bar signal (machine formats available) |

### 9.5 MCP server

crewmind is itself an MCP server, so a person can run it from any MCP client.

- **IF-5.1 Transport and auth.**
  - Streamable HTTP at one endpoint.
  - Clients authenticate with a minted bearer token, or OAuth 2.1: authorization code with PKCE, dynamic client registration, and audience-bound tokens per RFC 8707.
  - The server must resist PKCE stripping, code replay, redirect swap, audience confusion and scope widening at the token endpoint.
  - Each step (register, approve, token, revoke) is an operation in the catalog; the standard endpoints are adapters over them. The person approves a client in their own signed-in session. A code presented with a wrong verifier, redirect or audience is spent.
- **IF-5.2 Scopes.** Four scopes, with `read` implied by every other one. A client sees only its person's projects. Tools outside the client's scope are not listed, and answer as unknown.

| Scope | Grants (minimum) |
| --- | --- |
| read | Whoami; list projects; the desk; overview; plan; budget and receipts; board; deliverables and artifacts; evidence; org; channels and chat history; memory; the record |
| steer | Chat with any agent; slash commands (pin, decide, fix, example, grill, do, hold, resume); upload files; decide items; acknowledge flags; lifecycle (start, hold, resume, stop, reopen, complete); edit memory |
| create | Search roles and crews; read a source URL; grade a goal; rehearse a spec; create a project from a spec; quick project and its status; clone a project |
| configure | Roster and hiring; skills; budget and quality; settings; data sources (minus human-only verbs); credential names and grants |

- **IF-5.3 Two-phase confirmation.** An irreversible write cannot happen in one call. The first call returns a preview and a confirm token bound to a hash of the tool and its exact arguments; the second call spends it. The token is single-use with a 5-minute life.
- **IF-5.4 Attribution.** Every MCP write is recorded permanently as machine-mediated ("person via mcp:\<client name>"), distinct from the same person acting directly.
- **IF-5.5 Untrusted content.** All agent-written text returned to a client travels inside a labelled envelope naming its author. Text that contains the envelope's closing marker is defanged before wrapping.
- **IF-5.6 Human-only verbs.** These require the person, not their model client:
  - allowing a write-capable data-source tool;
  - creating or revealing a credential value (a secret's value is never revealed to anyone, CON-2);
  - signing in to an MCP server with OAuth, and adding an MCP server started from a command (CON-10, CON-11);
  - deleting a connection (CON-1);
  - changing project membership;
  - handing on the chair;
  - deleting a project;
  - approving a skill version.

  MCP may show these as waiting on the person but cannot perform them.
- **IF-5.7 Context budget.**
  - Tools summarise by default: about 600 characters per string, 20 items per list and 6,000 characters per payload.
  - Full detail is returned on request: about 20,000 characters per string, 200 items and 40,000 characters.
  - Any truncation is marked in the payload; silent truncation is forbidden.
- **IF-5.8 Resources and prompts.** Expose the desk and each project as resources, plus the Founder doctrine and goal grammar (FND-7) as documents. Provide prompts for: design a project, today's brief, why a project is at risk, and a spot audit. The doctrine served here is the same single copy the Founder uses.

### 9.6 Agent API

The only way an agent affects anything. It is exposed over HTTP, and inside the sandbox as an MCP tool server the harness mounts.

- **IF-6.1** Every call carries the run token. Every refusal is a 403 with the shared error envelope, and counts toward the run's refusal cap (unless warn-only).
- **IF-6.2** No agent-facing response may contain a secret value. A test walks the agent schema and fails if any field shaped like a secret appears outside a named allowlist.
- **IF-6.3** Capability groups the agent API MUST offer (the role decides which a given agent may use):
  - **Context:** whoami, the context pack, the board, recent activity, and loading granted skills (LIB-6).
  - **Work:** create, claim, complete, review, block and kill tasks; file evidence and search records; gap reviews.
  - **Artifacts:** publish, supersede, read (paged); declare test files.
  - **Team:** list the role library; hire, stand down and recall teams (CEO only).
  - **Conversation:** list channels, read and post messages, post action cards, cite a directive.
  - **Memory:** write and search recall memory; write own pinned notes; propose standing orders (CEO).
  - **Planning:** propose requirements and dependencies; propose or reset a commitment; set a cycle goal; open bets and publish findings; write review narratives; file mistake reports; draw the CEO reserve (GOV-10); record decisions the agent itself is authorised to take.
  - **Asking the chairman:** approvals, questions, heads-ups, assists, capacity requests, tool-permission requests, reopen requests, allowlist requests.
  - **Outside world:** data-source gateway calls; side effects (two-phase); launches and their watches; reading and sending mail from the agent's own address (INT-10); browser actions (EXE-17); A2A tasks through the gateway (INT-11).
  - **Credentials:** list the names granted to the role; request re-scoping.

### 9.7 Inbound and outbound integrations

- **IF-7.1** Webhook intake verifies a per-project signature and a replay window before storing anything. GitHub events are supported natively; any signed generic JSON otherwise.
- **IF-7.2** Outbound notifications (push, Slack, email) are clients of the same operations, and never carry decisions the person cannot also see and take in the app and API.

### 9.8 Parity matrix

| Capability | App | API | CLI | MCP | Slack |
| --- | --- | --- | --- | --- | --- |
| Chat with the CEO or any agent | yes | yes | yes | steer | yes |
| Slash commands (pin, decide, fix, example, do, hold) | yes | yes | yes | steer | yes |
| Upload files and images | yes | yes | yes | steer | yes |
| Draft and create projects (chat, quick, from spec) | yes | yes | yes | create | no (link to app) |
| Rehearse a spec | yes | yes | yes | create | no |
| Lifecycle: start, hold, resume, stop, reopen, complete | yes | yes | yes | steer | start, hold, resume |
| Decide items and audits | yes | yes | yes | steer | yes (cards) |
| Read plan, board, org, runs, evidence, record, brief, agenda | yes | yes | yes | read | brief and links |
| Deliverables and artifacts | yes | yes | yes | read | links |
| Memory: view, edit, forget | yes | yes | yes | read; edit with steer | no |
| Budget, receipts, ledger | yes | yes | yes | read | summary |
| Budget, quality, settings, roster | yes | yes | yes | configure | no |
| Data sources and credentials | yes | yes | yes (values via hidden input) | configure, minus human-only verbs | no |
| People and membership | yes | yes | yes | no (human-only) | no |
| Delete a project | yes | yes | yes | no (human-only) | no |
| Install operations (backup, restore, key rotation) | no | no | host-local | no | no |
| Email: mail servers, project mailboxes, agent addresses, allowlist | yes | yes | yes (passwords via hidden input) | configure, minus passwords and admin keys (human-only) | no |
| Skills, A2A endpoints, OpenTelemetry export | yes | yes | yes | configure (skill approval and endpoint credentials human-only) | no |
