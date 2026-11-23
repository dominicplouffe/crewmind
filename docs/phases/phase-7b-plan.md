# Phase 7.B plan: secrets, variables and MCP servers

Status: **planned on 23 Nov 2026. Waiting for the owner's answers** (end of this file). Nothing in this plan is built.

Goal: a project can be given the secrets, variables and MCP servers its work needs, the Founder and the crew know what they have, a project that lacks something it needs cannot start, and no secret value ever reaches a model, a trace, a chat, an artifact, an export or a log.

## Why this phase exists

The first real project on the server was a daily WordPress blog. It started, its crew ran, and it could never publish: nothing anywhere accepts a WordPress password, and nothing stopped the start. The tokens spent were wasted. Phase 7.B is inserted before phase 8 because without it most real projects cannot do their job.

## How this was missed

A review of the code and the records, 23 Nov 2026.

| # | Finding | Where |
| --- | --- | --- |
| 1 | EXE-13 has two halves: what must never enter a sandbox, and the role credentials that must. Phase 2 built and tested only the first. `traceability.csv` marks EXE-13 **done** on the strength of `test_P3_no_sandbox_holds_a_provider_key`, which proves only that nothing gets in. | `docs/traceability.csv` EXE-13 |
| 2 | The deferral was written in footnotes, not in the plan. The phase 7 outcome and LIB-4's note say role credentials "grant nothing until phase 8", but phase 8's list in `PLAN.md` does not contain EXE-13. It was in no phase's to-do list. | `phase-7-plan.md`, `PLAN.md` |
| 3 | The spec never says how a role credential is created, owned, granted, changed or removed. EXE-13 only says what happens once one exists. An honest phase 2 would have had to stop and ask. | `06-10-execution-EXE.md` |
| 4 | Creating a project from the Founder filters the missing role credentials **out** of what blocks the start, by matching the words "not available in this version". So `can_start` is true for a project that cannot work. | `src/crewmind/domain/founder/operations.py:579` |
| 5 | The project start-check registry (PRJ-1) is empty. Phase 1 built it for later phases; none added a check. Nothing is checked when any project starts. | `src/crewmind/domain/projects/lifecycle.py:46`, `operations.py:282` |
| 6 | The credential grants a spec carries are stored in `project.extras["credentials"]` and read only by export. No code uses them. | `src/crewmind/domain/library/transfer.py:136-140` |
| 7 | Four shipped roles declare credentials: `github` (engineer, game-developer, market-data-engineer), `market-data` (five finance roles), `wordpress` (blog-writer), `news-api` (market-news-analyst). The Founder staffs them freely; nothing tells the chairman. | `content/roles/*.json` |
| 8 | The role tool grant `data` (for data sources) exists in the role format and grants nothing. | `src/crewmind/domain/library/documents.py:25` |
| 9 | Data sources (INT-4) are planned for phase 8 and not started. Their spec allows no auth, bearer and OAuth, but not a custom header, and says nothing about servers on a private network. | `06-15-integrations-INT.md` |
| 10 | The secret store seals each value with AES-256-GCM but binds it to nothing. Someone who can write to the database could move one secret's ciphertext onto another row (for example a project secret onto a model credential) and it would decrypt. | `src/crewmind/domain/secrets/store.py:65` |
| 11 | The tests that keep secrets out of outputs check field **names** (`SECRET_WORDS`), not values. A value that reaches an agent through a field called `text` or `body` would pass. Nothing scans agent-visible text for a known secret. | `tests/attack/test_secrets.py:58` |
| 12 | IF-4.7 is marked done, but it prompts only for model credentials, because that is the only kind there is. FND-13 is partial for the same reason. | `docs/traceability.csv` |

What is sound and is reused: the secret store and key rotation; the rule that a sandbox's environment is built from nothing (`sandbox_environment`); the outbound fetch guard that resolves a host, refuses private addresses and connects only to the address it checked (`domain/work/fetch.py`); the tool-permission decision kind with its deny default (HUM-2); the refusal cap; the side-effect ledger; the MCP SDK already in the stack (version 2.3.0, which ships an MCP client and an OAuth client).

**Process fix, kept beyond this phase:** a requirement is marked done only when a test proves every sentence of it, and a deferral is written into `PLAN.md` under the phase that takes it, never only in a note. The phase 7.B outcome checks every `done` in `traceability.csv` against this rule.

## Words used in this plan

- **Secret:** a named value an agent's work needs and nobody should read, such as a WordPress application password. Write-only: once saved it is never shown again, to anyone.
- **Variable:** a named value that is not secret, such as the WordPress site address. Shown to people and to agents.
- **MCP server:** an outside server that speaks the Model Context Protocol and offers tools. The spec calls it a data source (INT-4); this plan proposes the plain name "MCP server" everywhere a person sees it.
- **Grant:** which roles of a project receive a secret, a variable or an MCP server. Nothing is granted by default.
- **Vault:** where a person keeps their secrets and MCP servers, to attach to any of their projects. (Question 1.)

## Exit demo

On a real install, with the reference WordPress brief:

1. The Founder drafts the project and says it needs a WordPress secret and the site address. The draft's review screen lists them as missing.
2. Create works; **start is refused**, naming what is missing, with a button to add each one.
3. The chairman adds the secret (value pasted once, never shown again), the variable, and one MCP server of each auth kind (none, bearer, custom header, OAuth). Each MCP server is tested on save, and its tools are listed with read tools allowed and write tools denied.
4. The project starts. The blog-writer's run publishes a draft post through the WordPress REST API with the secret; an agent calls a read tool of an MCP server; a call to a denied write tool is refused without leaving the server, and the agent's request for it becomes an approval on the desk.
5. The secret's value appears in no model request, run step, trace, chat message, memory, artifact, export, clone, backup in clear, event or log line. An automated test checks every one of these.
6. The chairman rotates the secret; the next run uses the new value. A revoked OAuth sign-in turns into one alarm with a "sign in again" button.

## Parts

Each part ends with both databases green, lint and type checks clean, attack tests for every rule it adds, and one concern per commit.

| Part | Builds | Demo |
| --- | --- | --- |
| **7B.0 Honest record, honest start** | The fixes that need no new feature: correct `traceability.csv` (EXE-13, INV-6, IF-4.7, FND-13, LIB-4, PRJ-1); remove the words-matching filter of finding 4; the first real start checks (a missing model credential, a missing declared secret); bind each secret's ciphertext to its owner and name (finding 10), with a migration that re-seals existing values | A project whose roles need a credential it does not have cannot start, and the refusal says what to add |
| **7B.1 Secrets and variables** | The vault, project attachment and role grants; write-only values; rotation; the operations and their surfaces; events | Add, grant, rotate, revoke and delete a secret from the web, the CLI and the API; an MCP client sees names only |
| **7B.2 Secrets in runs** | Injection into granted runs as environment variables or files on the in-memory private filesystem; the scrubber at every point agent text enters the platform; warm sessions restart on a change | The WordPress publish run works; the value is in nothing stored |
| **7B.3 MCP servers** | Connecting a server over Streamable HTTP with each auth kind; the OAuth client; testing a connection; tool discovery and classification; health, the circuit breaker and re-sign-in | Four servers, one per auth kind, connected and tested from the web |
| **7B.4 MCP tools in runs** | The gateway that proxies tool calls; tools offered per role grant and permission; denied calls refused on the server; permission requests as approvals; results as untrusted input; limits, metering and records | An agent uses a read tool; a write tool is refused and requested; the chairman allows it |
| **7B.5 The Founder and the project know** | The Founder lists what exists and drafts grants; the draft and review screens show what is needed; the setup checklist and start blocking on every surface; the context pack names what a run has; the project page banner | The exit demo, steps 1 to 4 |
| **7B.6 Hardening and the acceptance test** | The leak test across every store; SECURITY.md; doctor checks; the exit demo as an acceptance test; the outcome section | The exit demo, all steps |

## Ownership and scope

Recommendation (Question 1): **secrets and MCP servers live in the person's vault and are attached to projects**, the way model credentials already work. A GitHub token is entered once and used by several projects. An admin may also add install-wide ones that any person can attach. A project shows what is attached to it, with role grants, and has a shortcut to add a new one straight into it.

- Only the owner of a vault item, or an admin for install-wide items, changes or deletes it.
- Only the project's chairman (or a co-chair) attaches an item and changes grants. Agents never do; the CEO may *request* a grant (IF-6.3), which becomes an approval.
- Removing an item from the vault detaches it everywhere, with a list of the projects affected shown before confirming.
- Variables follow the same model. A variable may also be set per project without the vault, since most are project-specific (the site address).

## Data model

New tables, all with timezone-aware times and every change written to the event log in the same transaction (INV-21). Values live only in the existing `secrets` table, encrypted.

| Table | Holds |
| --- | --- |
| `vault_items` | id, kind (`secret`, `variable`, `mcp_server`), name, description (what it is for, shown to agents), owner (a person, or the install), state, created and changed times, last used, health |
| `vault_secrets` | for a secret: shape (`text` or `file`), suggested environment variable name or file name, the hosts it is meant for (optional, shown to agents and used by the scrubber's report) |
| `vault_variables` | for a variable: its value (plain) |
| `mcp_servers` | URL, transport, auth kind (`none`, `bearer`, `header`, `oauth`), custom header name, OAuth metadata (issuer, client id, scopes, audience), private-address allowed flag, breaker state, last tools refresh |
| `mcp_tools` | server, tool name, title, description (as the server gave it), input schema, annotations, classification (`read`, `write`, `unknown`), permission (`allowed`, `denied`), first seen, last seen |
| `project_attachments` | project, vault item, environment variable name or file name in this project, attached by, attached at |
| `attachment_grants` | attachment, role slug (or `*` for every role of the project) |
| `requirements_declared` | what a project needs that it does not yet have: kind, name, roles, source (a role's declaration, the spec, the CEO's request) |

The secret values for a vault item, an MCP server's bearer token or header value, and its OAuth access and refresh tokens, are rows in `secrets` with owner kinds `vault_secret` and `mcp_server`. No value is ever stored anywhere else.

## Operations

Each is one catalog operation (P11) with the web, CLI, HTTP and MCP adapters. Values are typed `SecretStr` on input and are never returned.

| Operation | Who | MCP client |
| --- | --- | --- |
| `vault.add_secret`, `vault.set_secret_value` | the owner; admin for install items | **No** (IF-5.6: creating a credential value is human-only) |
| `vault.add_variable`, `vault.change_variable` | the owner | configure scope |
| `vault.add_mcp_server` (none, bearer, header) | the owner | **No** for bearer and header (they carry a value); configure scope for none |
| `vault.connect_mcp_oauth` / the OAuth callback | the owner, in a browser | **No** |
| `vault.test_mcp_server`, `vault.refresh_mcp_tools` | the owner | configure scope |
| `vault.list`, `vault.show` | anyone who can see the item | read scope (names, kinds, health, never values) |
| `vault.delete` | the owner | **No** (irreversible; two-phase on other surfaces) |
| `projects.attach`, `projects.detach`, `projects.grant`, `projects.revoke` | the chairman | configure scope |
| `mcp.set_tool_permission` | the chairman | configure scope to deny; **no** to allow a write tool (IF-5.6) |
| `agent.list_secrets` (names and descriptions of what this run has) | agent | — |
| `agent.request_access` (a secret, variable, server or tool) | agent | — |
| `agent.mcp_call` (and the tools it exposes) | agent | — |

## How a secret reaches a run

- At lease, the runner reads the secrets granted to the seat's role in this project, and nothing else (EXE-13).
- **Text secrets** are given as environment variables under the name set on the attachment (for example `WORDPRESS_APP_PASSWORD`). **File secrets** are written to the run's private in-memory filesystem (`/run/crewmind`, mode 0700, no exec), with an environment variable holding the path. Names are checked: letters, digits and underscores; no `CREWMIND_`, `PATH`, `HOME`, `LD_`, `PYTHON`, `NODE_OPTIONS` or other name that changes how a program runs.
- **Variables** are given as environment variables and are listed by name and value in the context pack.
- The context pack lists each granted secret by name, description and variable name, never its value, so the agent knows what it may use and for what.
- Changing, rotating or revoking anything granted to a seat ends that seat's warm chat process (the existing 7.15 rule), so the next run sees the change.
- **The scrubber.** The server keeps, for each live run, the values it injected. Every way agent text enters the platform passes through one function that replaces any of those values with `[secret: NAME]`: model requests at the gateway (so the provider never receives a value the agent printed), run steps, traces, chat posts, memory notes, evidence, task completions, side-effect records, and the workspace snapshot that turns files into artifacts. A file that contained a value is stored scrubbed, and the chairman is told once, naming the file and the secret, not the value. Values shorter than `secret.min_length` \[8\] are refused when saved, because a short value cannot be scrubbed without breaking ordinary text.
- **What this does not prevent, stated in SECURITY.md:** a secret given to a sandbox can be sent anywhere by the agent, because egress is open (EXE-14). The scrubber stops it being stored or sent to the model provider through crewmind, not exfiltration over the network. Secrets for HTTP APIs that can be reached through an MCP server should be put there instead, where the agent never sees them (Question 4).
- **Command-line agent logins** (the parked work) are a different, stated exception (LLM-8) and are not part of this phase.

## How an agent reaches an MCP server

- **Never directly.** The server's address, token, header and OAuth tokens stay on the platform (INT-4). The agent calls the agent API; the platform's MCP gateway makes the call.
- **Transport:** Streamable HTTP, with the older HTTP+SSE as a fallback for servers that only speak it. Servers started as a local command (stdio) are not in this phase (Question 3).
- **Addresses:** https only, except plain http to `localhost`. Public addresses through the existing fetch guard (resolve, refuse private, connect to the checked address, no redirects to new hosts). A server on a private network is allowed only when an admin turns it on for that server, because it lets crewmind reach inside the network it runs in (Question 2).
- **Auth kinds:**
  - **None.**
  - **Bearer:** `Authorization: Bearer <token>`.
  - **Custom header:** a header name and value, for servers that read keys from `X-API-Key` and the like. Header names are checked: no `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Cookie` overrides of the platform's own, or `Mcp-Session-Id`.
  - **OAuth:** the MCP authorization flow. The platform discovers the authorization server from the MCP server's protected-resource metadata, registers itself as a client where the server allows dynamic registration (otherwise the chairman pastes a client id and, if needed, a secret), and sends the chairman's browser through authorization code with PKCE S256, a single-use `state`, and the resource indicator (audience binding). The callback is `<public URL>/oauth/mcp/callback`, so OAuth needs the install's public https address. Access and refresh tokens are stored as secrets; refresh happens in the gateway before expiry and on a 401; a refresh token the provider rotates replaces the old one. A refused refresh marks the server **needs sign-in**, raises one alarm with a "sign in again" button, and every call meanwhile returns a plain message to the agent.
  - The tokens act as the chairman's account at that provider. The page says so before sign-in.
- **Tools offered to an agent:** those of servers attached to the project and granted to the seat's role, with permission `allowed`. They appear in the agent's tool list as `mcp_<server>_<tool>`, with the server's description wrapped as untrusted text (P4) and shortened to `mcp.description_max` characters.
- **Classification on discovery:** a tool whose MCP annotations say read-only and not destructive starts `allowed`; anything else, or no annotations, starts `denied` (INT-4). The annotations are the server's claim, not proof, so the chairman sees the classification and can change it. A tool that appears later starts as its classification says, and the chairman is told once. A tool that disappears is kept, marked gone.
- **A denied call** never leaves the server, is refused with the tool-permission rule, counts toward the run's refusal cap (EXE-10), and the refusal tells the agent it may request access.
- **Results** come back as untrusted input, cut to `mcp.result_max_bytes` with the cut marked (never silent), images and resources passed as text descriptions in this phase. A result that is an error (`isError`) is passed back as such and does not count toward the refusal cap.
- **Write tools as side effects:** a call to a tool not classified read-only is recorded in the side-effect ledger with an idempotency key, so a retried run never repeats it (WRK-16, INV-14).
- **Limits:** `mcp.call_timeout` per call, `mcp.max_calls_per_run`, `mcp.max_calls_per_day` per project, counted in the ledger like web searches (count, not tokens). A server that keeps failing opens a circuit breaker on the same rules as model credentials (LLM-11).

## The Founder and the project

- The Founder's `list_credentials` tool becomes `list_connections`: model credentials, secrets, variables and MCP servers the chairman has, by name and description, never values.
- Roles keep declaring what they need (`credential_names`). The draft states what the roster needs (FND spec line "the draft states up front which credentials the roster needs"), whether the chairman already has it, and proposes grants by role.
- The review screen lists each need as **have it** or **missing**, with "add it now" in place.
- **Start is refused** while anything declared is missing, on every surface, with the list and a link to add each (PRJ-1 start check). The chairman may instead remove the role that needs it. There is no "start anyway" (Question 5).
- A running project whose secret is removed, or whose MCP server needs sign-in, shows a banner on its page naming what broke and what to do; seats that depend on it are held with the reason shown (EXE-4), not left to fail.
- The CEO's context pack lists what the project has and what its roles declared but lack, so it can plan around a gap and ask for it.

## Web screens

Designed for a laptop screen and wider, usable on a phone.

- **Settings → Secrets & variables** and **Settings → MCP servers** (the vault): a table of items with kind, where used, health, last used and owner. "Add" opens a side sheet.
- **Add a secret:** name, what it is for (one line agents will read), shape (text or file), suggested variable name (filled in from the name), the value in a password field or a file picker, and a note: "You will not be able to see this again. You can replace it." Saving shows where it can be attached.
- **Add a variable:** name, value, what it is for.
- **Add an MCP server:** URL; an auth choice of four cards (No auth / Bearer token / Custom header / OAuth sign-in), each revealing only its own fields; **Test connection**, which shows the server's name, version and tools before anything is saved; then the tools table with each tool's classification and an allow switch (write tools need a confirmation). OAuth opens the provider's sign-in in a new window and returns to the sheet.
- **Project → Connections tab:** what is attached, with a role grant picker per item ("All roles" or chosen roles), what the roster declared and lacks (red, with "Add"), MCP tools the project's agents may call, and pending access requests from agents.
- **Desk and chat:** an agent's access request is a decision card naming the agent, what it asks for and why, with Allow and Deny; a write tool's Allow needs the person, not their AI client.
- Every value field is a password field, never pre-filled, never logged by the browser (`autocomplete="off"`), and the value is cleared from memory after saving.

## Security and privacy measures

1. Values are encrypted at rest, sealed with the owner kind, owner id and name as associated data so a ciphertext cannot be moved to another row.
2. Values are write-only. No operation, screen or command shows one, to anyone, admins included. Replacing is the only way to change one.
3. Values never appear in an operation output, event, run step, trace, context pack, chat, memory, artifact, export, clone, spec, rehearsal, OpenTelemetry span or log line. A test seeds known values and scans every one of these stores after the exit demo.
4. Least privilege: nothing is granted by default; a grant names roles; a run gets only its role's grants in its own project.
5. Human-only: creating or replacing a value, connecting OAuth, allowing a write tool, deleting a vault item. MCP clients see names and health only.
6. The scrubber at every ingress of agent text, and refusal of values too short to scrub.
7. Reserved environment variable names refused.
8. MCP addresses guarded: https, public addresses only unless an admin allows a private one per server, the address checked at connect time, no redirects to other hosts, header names checked.
9. OAuth: PKCE S256, single-use state bound to the person's session, exact redirect, audience binding, refresh rotation honoured, tokens stored as secrets.
10. Everything an MCP server returns, including tool names and descriptions, is untrusted input (P4) and wrapped as such for the model.
11. A log filter on every handler replaces any known secret value as a second line of defence, and the code never formats a value into a message in the first place.
12. Backups keep values encrypted with the master key, as today. Exports and clones carry names, grants and descriptions only (LIB-4, PRJ-9).
13. SECURITY.md says plainly: a secret given to a sandbox can be exfiltrated over the open network; MCP servers keep their credentials out of the sandbox; OAuth tokens act as the chairman's account; private-network servers widen what crewmind can reach.

## Logging, records and error handling

- **Events** (no values, ever): secret added, value replaced, deleted; variable added, changed, deleted; MCP server added, tested, tools refreshed, tool permission changed, signed in, needs sign-in, breaker opened and closed, removed; attached, detached, granted, revoked; access requested and decided. Each names the actor, and whether it came through MCP (IF-5.4).
- **Run steps:** each secret injected, by name; each MCP call with server, tool, arguments, outcome (ok, error, refused, timed out), duration and result size, with arguments and results scrubbed.
- **Server logs:** one line per MCP connection failure and per OAuth failure, with the server's name and the reason, never a token, header value or full URL query.
- **What the agent is told:** a plain reason it can act on, for example "the WordPress server needs the chairman to sign in again; ask for it with request_access", never a stack trace, a token or an internal address.
- **What the chairman is told:** one alarm per broken thing (a server that needs sign-in, a secret a run tried to use after it was removed), with the fix as a button; repeated failures are counted, not repeated.
- **Health:** testing a server lists its tools; the daily upkeep re-tests attached servers and refreshes their tools; `crewmind doctor` reports servers that need sign-in and declared needs that are missing.

## Settings to add to Appendix A

| Setting | Default | Range | Scope |
| --- | --- | --- | --- |
| `secret.min_length` | 8 | 8–64 | install |
| `mcp.call_timeout` | 60 s | 5 s–10 min | project |
| `mcp.max_calls_per_run` | 100 | 1–1,000 | project |
| `mcp.max_calls_per_day` | 1,000 | 10–100,000 | project |
| `mcp.result_max_bytes` | 64 KB | 4 KB–1 MB | project |
| `mcp.description_max` | 1,000 characters | 100–4,000 | install |
| `mcp.tools_refresh` | daily | hourly, daily, weekly | install |

## Spec changes this phase would make

Proposed, to be applied only after the owner's answers, each with a CHANGELOG line:

- A new section, **6.17 Secrets, variables and MCP servers (SEC)**, with its own requirement ids, so the management of role secrets is specified, not implied: the vault, attachment and grants, write-only values, injection, the scrubber, variables, the start check, the Founder's part, and the screens.
- **INT-4** gains the custom-header auth kind, the transport, private addresses as an admin choice, write tools as side effects, and the plain name "MCP server".
- **EXE-13** points to SEC for how role secrets are managed.
- **7.18** gains the vault item and MCP server state tables; **PRJ-1** names the start checks; **FND-13** and **IF-4.7** cover secrets and MCP servers; **INV-6** names the scrubber; Appendix A gains the settings above.
- `PLAN.md` gains phase 7.B and moves INT-4 into it.

## Tests to write first

- Attack: a run of a role without the grant sees no secret, in its environment or its context pack; a run in another project of the same chairman sees none.
- Attack: an agent that prints a secret in a shell, posts it in chat, writes it to a file, puts it in evidence or memory, or sends it in a model request, leaves no copy in any store, and the provider receives `[secret: NAME]`.
- Attack: an MCP client cannot create or replace a value, allow a write tool, or connect OAuth; it can list names.
- Attack: a denied MCP tool call never reaches the server (the test server records every request), is refused with the rule, and counts toward the refusal cap.
- Attack: an MCP server URL that resolves to a private address, or redirects to one, is refused unless allowed by an admin; a reserved environment variable name is refused.
- Attack: a spec that carries a secret value is refused; an export of a project with secrets carries names only.
- State machine tables and property tests for the vault item, the MCP server and the tool permission.
- Contract: each auth kind against a local test MCP server (none, bearer, custom header, OAuth with a test authorization server issuing short-lived tokens and rotating refresh tokens).
- Scenario: a project whose roles declare a missing secret is refused at start on every surface; adding it lets it start.
- Scenario: rotating a secret restarts the warm seat and the next run gets the new value.
- The leak test of measure 3, across every store, after the exit demo.

## Risks

| Risk | Mitigation |
| --- | --- |
| The scrubber misses an encoded copy (base64, URL-encoded, split across lines) | Scrub the common encodings too; say in SECURITY.md that the scrubber is a safeguard, not a guarantee; prefer MCP servers for API credentials |
| OAuth flows differ between providers | Build on the MCP SDK's OAuth client; test against a local authorization server and two real public MCP servers before calling it done |
| MCP servers that only speak stdio are common | Stated as out of scope with the reason; a later phase runs them inside a container (Question 3) |
| Tool annotations are wrong or missing | Unknown means denied; the chairman sees and changes every classification |
| Scope grows into a general integration platform | The parts above are the whole phase; anything else goes to phase 8 |

## Out of scope

- MCP servers started as a local command (stdio), unless the owner answers Question 3 otherwise.
- Prompts and resources offered by MCP servers (tools only).
- Injecting secrets through an egress proxy so the agent never sees them (Question 4).
- Per-agent secrets inside a role, secret expiry dates, and an external secret manager (Vault, 1Password).
- Command-line agent logins (parked separately).

## Questions for the owner

1. **Where secrets and MCP servers live.** Recommendation: in each person's vault, attached to projects with role grants, plus install-wide items an admin adds. Alternative: per project only, simpler, re-entered for every project.
2. **MCP servers on a private network** (`localhost`, `192.168.x.x`, a Docker network). Recommendation: allowed per server only when an admin turns it on, with a warning. Alternative: always allowed, or never.
3. **Local-command (stdio) MCP servers**, such as those started with `npx`. Recommendation: not in 7.B; a later phase runs each inside its own container. Alternative: build it now, which makes the phase noticeably longer.
4. **API credentials the agent never sees.** Recommendation for 7.B: secrets go into the sandbox, scrubbed from everything stored, with the exfiltration risk stated; MCP servers are the safe path. Alternative: an injecting egress proxy (like the one this build environment uses), which is safer and noticeably more work.
5. **Starting with something missing.** Recommendation: refused, no override; the chairman adds it or removes the role. Alternative: allowed with a confirmation and the dependent seats held.
6. **Who may add install-wide items.** Recommendation: admins only. Alternative: any person.
7. **Default grant when a secret is attached.** Recommendation: the roles that declared it, or none if none did; the chairman widens it. Alternative: every role of the project.
