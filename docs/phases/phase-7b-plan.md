# Phase 7.B plan: secrets, variables and MCP servers

Status: **planned on 23 Nov 2026; the owner's answers are recorded (end of this file).** Building starts with 7B.0.

Goal: a project can be given the secrets, variables and MCP servers its work needs; the Founder and the crew know what they have; nothing runs that cannot work for lack of one; and no secret value ever reaches a model, a trace, a chat, an artifact, an export or a log. Most secrets never enter a sandbox at all.

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

## The three tests every decision here passes

The owner asked that each decision answer three questions: what would a world-class product do, what is right for the person using it, and what keeps the app sound as it grows. The answers below are the result. Where they differ from the first draft of this plan, the first draft was too timid.

## Words used in this plan

- **Secret:** a named value an agent's work needs and nobody should read, such as a WordPress application password. Write-only: once saved it is never shown again, to anyone. It can be replaced.
- **Variable:** a named value that is not secret, such as the WordPress site address. Shown to people and to agents.
- **MCP server:** an outside server that speaks the Model Context Protocol and offers tools. The spec's "data source" (INT-4) becomes "MCP server" everywhere a person sees it.
- **Scope:** where a secret, variable or MCP server lives: the **install** (an admin's, usable by everyone), a **person** (theirs, usable in any of their projects), or a **project** (that project only).
- **Grant:** which roles of a project may use something. A project uses only what is granted.
- **Sent for you:** a secret crewmind adds to an agent's HTTPS requests to one site, so the agent never sees it. The default for API keys and passwords.
- **Given to the agent:** a secret placed in the agent's sandbox, for what cannot be sent for it (an SSH key, a database password, a tool that reads its own config file). Masked in everything stored; the risk is stated.

## Exit demo

On a real install, with the reference WordPress brief:

1. The Founder drafts the project and says, in its first reply, that the crew needs a WordPress application password for `dplouffe.ca` and the site address. The review screen shows both as missing, each with **Add**.
2. Create works. **Start** shows what is missing and offers two buttons: **Add them now**, and **Start without them**, which says which agents will wait and why.
3. The chairman adds the password as a secret *sent for you* to `dplouffe.ca` (Basic auth with the WordPress user name), the site address as a variable, and one MCP server of each kind: a remote server with no auth, one with a bearer token, one with a custom header, one with OAuth sign-in, and one started from a command (`npx …`) that runs in its own container. Each is tested on save; its tools are listed, read tools allowed and write tools denied.
4. The project starts. The blog-writer publishes a draft post with plain `curl` to the WordPress REST API, **without the password ever entering its sandbox**: crewmind adds it on the way out. An agent calls a read tool; a call to a denied write tool is refused on the server, and the agent's request for it becomes an approval on the desk.
5. No secret value appears in any model request, run step, trace, chat message, memory, artifact, export, clone, spec, backup in clear, event, OpenTelemetry span or log line. A test checks every one.
6. The chairman replaces the password; the next request uses the new one. A revoked OAuth sign-in raises one alarm with **Sign in again**.

## Parts

Each part ends with both databases green, lint and type checks clean, attack tests for every rule it adds, and one concern per commit.

| Part | Builds | Demo |
| --- | --- | --- |
| **7B.0 Honest record, honest start** | Correct `traceability.csv` (done for EXE-13 and INT-4 already); remove the words-matching filter of finding 4; the start checks (a missing model credential, a missing declared need), with **start without them** holding the seats that need it; seal each secret to its owner and name (finding 10), re-sealing existing values in the migration | A project missing a declared credential is refused at start with what to add, or starts with the dependent seats held and the hold shown |
| **7B.1 Secrets and variables** | The three scopes, project attachment and role grants; write-only values with replace; optional expiry date with a reminder; paste a `.env` to add many at once; operations on every surface; events | Add, attach, grant, replace and delete from the web, CLI and API; an MCP client sees names only |
| **7B.2 Secrets in runs** | *Given to the agent*: environment variables, or files on the run's private in-memory filesystem. The scrubber at every point agent text enters the platform. Warm sessions restart on a change | A run uses a given secret; its value is in nothing stored and never reaches the model provider |
| **7B.3 Secrets sent for you** | The egress proxy: every connection of a run passes through it; connections to a site with a secret *sent for you* granted to that run are opened, the secret is added as a header, and the request goes on; every other connection is passed through untouched. The run's own certificate authority, trusted inside its sandbox | The blog-writer posts to WordPress with `curl` and no password in its sandbox |
| **7B.4 MCP servers, remote** | Streamable HTTP (with HTTP+SSE fallback); no auth, bearer, custom header and OAuth (discovery, dynamic or pasted client registration, PKCE, audience binding, refresh); testing; tool discovery and classification; health, circuit breaker and sign-in again | Four remote servers, one per auth kind |
| **7B.5 MCP servers, from a command** | Servers started from a command (`npx`, `uvx`, `docker run`), each in its own long-lived container of the tool image, with its secrets in that container and never in an agent's; started on first use, stopped when idle | A command server connected, tested and used |
| **7B.6 MCP tools in runs** | The MCP gateway: tools offered per grant and permission, denied calls refused on the server, access requests as approvals, results as untrusted input, write tools as side effects, limits, metering, records | An agent uses a read tool; a write tool is refused, requested and allowed |
| **7B.7 The Founder and the project know** | The Founder lists what exists and drafts needs and grants; the review screen and the start screen; the project's **Connections** tab; the setup checklist on every surface; the context pack names what a run has; banners for anything broken | Exit demo steps 1 to 4 |
| **7B.8 Hardening and acceptance** | The leak test across every store; SECURITY.md; doctor checks; presets for well-known MCP servers; the exit demo as an acceptance test; the outcome section | The exit demo, all steps |

## Scopes, ownership and grants

- **Three scopes, one model.** Install (an admin adds; any person may attach it), person (the owner adds; attachable to any project they chair), project (added inside the project; exists only there). This is how GitHub organisations, Vercel and Doppler do it, and it means a GitHub token is entered once.
- **Precedence is explicit, never silent.** If two attached items would give the same environment variable or the same site to the same role, attaching the second is refused with both named. No shadowing.
- **Who changes what.** The owner changes or deletes a person item; an admin an install item; the chairman (or a co-chair) a project item, attachments and grants. Agents change nothing; any agent may *request* access to something by name, and the request is an approval for the chairman.
- **Default grant.** The roles that declared the need are chosen for you; if none did, the chairman picks at least one role, or **All roles**, before attaching. Least privilege by default, never a useless secret.
- **Removing.** Deleting an item shows every project that uses it first; detaching is immediate; seats that depended on it are held with the reason.

## Data model

All times timezone-aware; every change writes its event in the same transaction (INV-21). Values live only in the existing `secrets` table, encrypted and sealed to their row.

| Table | Holds |
| --- | --- |
| `connection_items` | id, kind (`secret`, `variable`, `mcp_server`), scope (`install`, `person`, `project`), owner id, name, description (one line agents read), state, created, changed, last used, expires on (optional), health |
| `connection_secrets` | delivery (`sent_for_you`, `given`); for *sent for you*: the sites (exact hosts), the header kind (`bearer`, `basic` with a user name, `header` with a name); for *given*: shape (`text`, `file`) and the default environment variable or file name |
| `connection_variables` | the value |
| `mcp_servers` | kind (`remote`, `command`); for remote: URL, transport, auth kind (`none`, `bearer`, `header`, `oauth`), header name, OAuth issuer, client id, scopes, resource; for command: the command and arguments, the image, the secrets given to it; private-network allowed; breaker state; tools refreshed at |
| `mcp_tools` | server, name, title, description as given, input schema, annotations, classification (`read`, `write`, `unknown`), permission (`allowed`, `denied`), first seen, last seen, gone |
| `project_connections` | project, item, environment variable or file name in this project (for *given* secrets and variables), attached by, attached at |
| `connection_grants` | project connection, role slug or `*` |
| `project_needs` | what a project needs: kind, name, roles, source (a role's declaration, the spec, an agent's request), and whether it is met, waived for now, or open |

## Operations

One catalog operation each (P11), with web, CLI, HTTP and MCP adapters. Values are `SecretStr` inputs and are never returned.

| Operation | Who | MCP client |
| --- | --- | --- |
| `connections.add_secret`, `connections.replace_secret` | the item's owner; admin for install; chairman for project | **No** (IF-5.6) |
| `connections.import_env` (many secrets and variables from pasted `.env` text) | same | **No** |
| `connections.add_variable`, `connections.change_variable` | same | configure |
| `connections.add_mcp_server` | same | configure for no auth; **no** when it carries a value or a command |
| `connections.sign_in` and the OAuth callback | the owner, in a browser | **No** |
| `connections.test`, `connections.refresh_tools` | same | configure |
| `connections.list`, `connections.show`, `connections.usage` | anyone who can see it | read (names, kinds, health; never values) |
| `connections.delete` | the owner | **No** (irreversible, two-phase elsewhere) |
| `projects.attach`, `projects.detach`, `projects.grant`, `projects.revoke` | the chairman | configure |
| `projects.needs` (what is needed, met or open) | members | read |
| `projects.start` gains `without_missing` | the chairman | steer |
| `mcp.set_tool_permission` | the chairman | configure to deny; **no** to allow a write tool (IF-5.6) |
| `agent.connections` (what this run has: names, descriptions, variable names, sites, MCP tools) | agent | — |
| `agent.request_access` | agent | — |
| MCP tools themselves, as agent tools | agent | — |

## Secrets sent for you: the egress proxy

- Every run's outbound HTTP and HTTPS goes through the platform's egress proxy, named in the run's environment (`HTTPS_PROXY`, `HTTP_PROXY`) with the run's own token as the proxy credential, so the proxy knows which run, and so which grants, each connection belongs to.
- **Nothing is blocked or changed except what has a secret.** A connection to a site with no secret *sent for you* granted to this run is passed through as an opaque tunnel: crewmind does not read it. This keeps EXE-14's open egress and v1's lesson that blocked requests fail invisibly.
- A connection to a granted site is opened with a certificate for that site issued by the **install's own certificate authority**, which is trusted inside every sandbox (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`, and the system store of the agent image). The proxy adds the header (`Authorization: Bearer …`, `Authorization: Basic …` from the user name and the secret, or a named header), replacing any the agent sent, verifies the real site's certificate on the way out, and streams the answer back. HTTP/1.1 is offered to the agent; the proxy speaks what the site supports.
- Each injection is a run step: site, secret name, method, path without the query, status, time. Never the value.
- **Built in-house, small, on the libraries already in the stack** (`h11`, `cryptography`, asyncio). mitmproxy was considered and rejected: it would bring 26 packages into the process that holds the master key, among them a web framework, a console UI and an LDAP client. Recorded in ADR-0010.
- The certificate authority's key is a secret like any other: encrypted, never in a sandbox. Leaf certificates are short-lived and cached in memory only.
- Clients that pin certificates, or ignore the proxy variables, cannot use a secret *sent for you*; the add form says so and offers *given to the agent* instead. This is stated in SECURITY.md.

## Secrets given to the agent

- At lease, the runner reads the *given* secrets granted to the seat's role in this project and nothing else (EXE-13).
- Text secrets become environment variables under the name set on the attachment; file secrets are written to the run's private in-memory filesystem (`/run/crewmind`, mode 0700, no exec), with a variable holding the path. Names are checked: letters, digits and underscores; reserved names refused (`CREWMIND_*`, `PATH`, `HOME`, `LD_*`, `PYTHON*`, `NODE_OPTIONS`, `*_PROXY`, `SSL_CERT_FILE` and others that change how programs run).
- The context pack lists each by name, description and variable name, never the value.
- **The scrubber.** For each live run the server holds the values it gave. One function replaces any of them, and their base64 and URL-encoded forms, with `[secret: NAME]` at every point agent text enters the platform: model requests at the gateway (so the provider never receives a value the agent printed), run steps, traces, chat posts, memory notes, evidence, task completions, side-effect records, MCP call arguments, and the workspace snapshot that makes artifacts. A file that held a value is stored scrubbed and the chairman is told once, naming the file and the secret. Values shorter than `secret.min_length` \[8\] are refused when saved.
- SECURITY.md says plainly: a *given* secret can be sent anywhere by the agent over the open network; the scrubber stops crewmind storing it or sending it to the model provider, not exfiltration. That is why *sent for you* is the default.

## MCP servers

- **Never reached by an agent directly.** Addresses, tokens, header values, OAuth tokens and a command server's secrets stay on the platform (INT-4). The agent calls the agent API; the MCP gateway makes the call.
- **Remote servers:** Streamable HTTP, falling back to HTTP+SSE for servers that only speak it. https only, except http to `localhost`. Public addresses through the existing fetch guard (resolve, refuse private, connect to the checked address, no redirects to other hosts).
- **Private networks** (`localhost`, a LAN, a Docker network): allowed per server when an admin turns it on, with a warning that it lets crewmind reach inside its own network. Link-local and cloud metadata addresses (`169.254.0.0/16`, `fd00:ec2::254`) are refused always.
- **Auth kinds:** none; bearer; custom header (a name and a value; `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Cookie` and `Mcp-Session-Id` refused); OAuth, following the MCP authorization specification: protected-resource metadata, then the authorization server's metadata; dynamic client registration where offered, otherwise a pasted client id (and secret if required); authorization code with PKCE S256, single-use `state` bound to the person's session, the resource indicator for audience binding; the callback at `<public URL>/oauth/mcp/callback`, so OAuth needs the install's public https address (the form says so if it is missing). Tokens are secrets; refresh happens before expiry and on a 401; a rotated refresh token replaces the old one. A refused refresh marks the server **needs sign-in**, raises one alarm with **Sign in again**, and calls meanwhile return a plain message. The form says the tokens act as the chairman's account at that provider.
- **Command servers:** a command and arguments (`npx -y @modelcontextprotocol/server-github`), the secrets it needs as environment variables, and an image (the tool image by default, with Node, Python, `uv` and `npx`). Each runs in its own container, on its own network with egress, with no workspace, no master key and nothing of any agent's; the platform talks to it over standard input and output. Started on first use, stopped after `mcp.command_idle` \[15 min\] unused, restarted after a crash with the breaker's back-off. Without Docker (unisolated mode), command servers are offered only for development, as a plain process, with the warning shown.
- **Discovery and classification:** a tool whose annotations say read-only and not destructive starts **allowed**; anything else, or none, starts **denied** (INT-4). Annotations are the server's claim, so the chairman sees and can change every classification. A tool that appears later starts as its classification says and the chairman is told once; a tool that disappears is kept, marked gone.
- **In a run:** tools of servers attached and granted to the seat's role, with permission allowed, appear as `mcp_<server>_<tool>`; descriptions are wrapped as untrusted (P4) and cut to `mcp.description_max`. A denied call never leaves the server, is refused with the tool-permission rule, counts toward the refusal cap (EXE-10), and tells the agent it may request access. Results are untrusted input, cut to `mcp.result_max_bytes` with the cut marked; images and embedded resources are described as text in this phase. An `isError` result is passed back as such and is not a refusal.
- **Write tools are side effects:** a call to a tool not classified read is recorded in the side-effect ledger with an idempotency key, so a retried run never repeats it (WRK-16, INV-14).
- **Limits and metering:** `mcp.call_timeout`, `mcp.max_calls_per_run`, `mcp.max_calls_per_day` per project, counted in the ledger like web searches. A server that keeps failing opens a circuit breaker on the same rules as model credentials (LLM-11).
- **Presets:** a curated, versioned list of well-known MCP servers (address or command, auth kind, the secrets they need, a link to get a key), shipped as library content and editable by admins, so adding GitHub or Sentry is two clicks and a paste.

## The Founder and the project know

- The Founder's `list_credentials` becomes `list_connections`: model credentials, secrets, variables and MCP servers the chairman can attach, by name and description.
- Roles declare what they need by name (`credential_names` today; extended to kinds: a secret for a site, a variable, an MCP server). The Founder's first reply names what the crew will need; the draft lists each need as **have it** or **missing**, and proposes grants.
- **Start:** if anything is missing, start shows the list with **Add them now** and **Start without them**. Starting without holds exactly the seats whose roles need what is missing, each hold naming the missing item (EXE-4), and puts one item on the desk. Adding the missing item lifts the hold by itself. No seat ever runs and fails for lack of a credential.
- A running project whose item is deleted, expires or needs sign-in shows a banner naming what broke and the fix; dependent seats are held, not left to fail.
- The CEO's context pack lists what the project has and what its roles need but lack, so it plans around a gap and asks for it.

## Experience

The bar: someone who has never seen crewmind adds a WordPress password the safe way, connects an OAuth MCP server and starts the project in under three minutes, without reading documentation, and never wonders whether a secret is safe. Every screen follows the design system (`docs/design/design-system.md`); keyboard first; WCAG 2.2 AA.

- **Where things are.** Settings gains **Connections** (install and personal items, in tabs). Each project gains a **Connections** tab: what this project uses, what its crew needs and lacks, and agents' access requests. One component set serves both.
- **The empty state teaches.** "Your crew uses connections to reach the outside world: a secret crewmind sends for you, a variable, or an MCP server's tools." Three cards, each with one sentence and **Add**.
- **One "Add" flow, three kinds,** in a side sheet:
  - *Secret.* Name; "What is it for?" (one line, agents read it); **How should crewmind use it?** as two cards: **Send it for me** (recommended; "to sites you choose; your agents never see it") with site, and auth style chosen from Bearer / Basic (with user name) / Header (with name); or **Give it to the agent** ("for keys a program reads itself; masked everywhere, but the agent could send it elsewhere"). The value field is a masked input with a paste button and a strength-free length check, and the line "You won't be able to see this again. You can replace it." **Who can use it** shows the roles that need it already chosen.
  - *Variable.* Name, value, what it is for.
  - *MCP server.* A preset picker with search ("GitHub", "Sentry", "Linear"…) or **Custom**. For custom: **Remote** (a URL) or **Command** (a command line). Auth as four cards, each revealing only its fields: **No auth**, **Bearer token**, **Custom header**, **OAuth sign-in**. **Test connection** shows the server's name, version and tools before anything is saved. Then **Tools**: a table with each tool's name, what it does, **Reads** or **Changes things**, and an allow switch; allowing a tool that changes things asks once, in words: "Agents will be able to … on <server>. Allow?"
  - **Paste a .env** on the secrets tab: a text area that turns `KEY=value` lines into a reviewable table (secret or variable, guessed from the name, changeable) before anything is saved.
- **Status at a glance.** Each item shows a health dot with a word (Working, Needs sign-in, Failing, Expires in 5 days, Never used) and "last used 2 h ago by Zoe, blog-writer". A secret's detail shows where it is used and its history (added, replaced, attached), never its value.
- **In the project.** The Connections tab leads with what is missing, in red, each with **Add** that opens the same sheet pre-filled with the need ("WordPress application password, for dplouffe.ca, used by blog-writer"). Grants are chips per item, editable in place.
- **In the draft and at start.** The review screen and the start dialog list needs with have-it / missing and **Add** in place, so nobody hunts.
- **Access requests.** An agent's request is a decision card in the chat and on the desk: who asks, for what, why, what allowing changes, **Allow** and **Deny**.
- **Copy rules.** Never "credential", "data source" or "MCP" alone where a plainer word fits: "secret", "variable", "MCP server", "tool". Every error says what to do next.
- **Safety in the browser.** Values are typed into fields that are never pre-filled, have `autocomplete="off"`, are cleared after saving, and are never put in a URL or local storage.

## Security and privacy measures

1. Values encrypted at rest and sealed with the owner kind, owner id and name as associated data, so a ciphertext cannot be moved to another row.
2. Write-only values: no operation, screen or command shows one, to anyone. Replacing is the only change.
3. Values never appear in an operation output, event, run step, trace, context pack, chat, memory, artifact, export, clone, spec, rehearsal, span or log line. A test seeds known values and scans every one of these after the exit demo.
4. Least privilege: nothing granted by default without a role; a run gets only its role's grants in its own project.
5. *Sent for you* is the default, so most secrets never enter a sandbox.
6. Human-only: creating or replacing a value, signing in to OAuth, adding a command server, allowing a write tool, deleting an item.
7. The scrubber at every ingress of agent text; values too short to scrub refused.
8. Reserved environment variable names refused; collisions refused.
9. MCP addresses guarded; private networks per server by an admin; metadata addresses never; header names checked.
10. OAuth: PKCE S256, single-use state bound to the session, exact redirect, audience binding, refresh rotation, tokens as secrets.
11. Command servers isolated in their own containers, with no workspace and nothing of any agent's.
12. Everything an MCP server returns, names and descriptions included, is untrusted input (P4).
13. A log filter on every handler replaces any known value as a second line of defence; no code formats a value into a message.
14. Backups keep values encrypted under the master key; exports, clones and specs carry names, grants and descriptions only.
15. SECURITY.md states every remaining edge: *given* secrets can be exfiltrated; pinned clients bypass *sent for you*; OAuth tokens act as the chairman's account; private-network servers widen reach; command servers run third-party code.

## Logging, records and error handling

- **Events** (never values): item added, replaced, changed, expired, deleted; attached, detached, granted, revoked; MCP server tested, tools refreshed, tool permission changed, signed in, needs sign-in, breaker opened and closed; need waived, met; access requested and decided. Each names the actor and whether it came through MCP (IF-5.4).
- **Run steps:** each *given* secret by name; each *sent for you* injection (site, name, method, path, status); each MCP call (server, tool, scrubbed arguments, outcome, duration, result size).
- **Server logs:** one line per MCP connection or OAuth failure and per proxy upstream failure, with the server or site and the reason; never a value, header, token or query string.
- **The agent is told** a plain reason it can act on ("the WordPress password has not been added yet; ask the chairman with request_access"), never a stack trace, a value or an internal address.
- **The chairman is told** once per broken thing, with the fix as a button; repeats are counted, not repeated.
- **Health:** testing lists tools; the daily upkeep re-tests attached servers, refreshes tools and warns of expiry; `crewmind doctor` reports servers needing sign-in, failing proxies and open needs.

## Settings to add to Appendix A

| Setting | Default | Range | Scope |
| --- | --- | --- | --- |
| `secret.min_length` | 8 | 8–64 | install |
| `secret.expiry_warning` | 7 days | 1–60 days | install |
| `mcp.call_timeout` | 60 s | 5 s–10 min | project |
| `mcp.max_calls_per_run` | 100 | 1–1,000 | project |
| `mcp.max_calls_per_day` | 1,000 | 10–100,000 | project |
| `mcp.result_max_bytes` | 64 KB | 4 KB–1 MB | project |
| `mcp.description_max` | 1,000 characters | 100–4,000 | install |
| `mcp.tools_refresh` | daily | hourly, daily, weekly | install |
| `mcp.command_idle` | 15 min | 1 min–24 h | install |
| `proxy.certificate_life` | 24 h | 1–168 h | install |

## Spec changes

Applied with this plan's answers, each with a CHANGELOG line:

- A new section, **6.17 Connections: secrets, variables and MCP servers (CON)**, with its own requirement ids, so the management of role secrets is specified, not implied.
- **INT-4** points to CON for MCP servers and keeps the permission rules; **EXE-13** points to CON for how secrets reach a run; **EXE-14** names the egress proxy and that it changes only connections to sites with a secret *sent for you*.
- **7.18** gains the connection item, MCP server and need state tables; **PRJ-1** names the start checks and starting without what is missing; **FND-13** and **IF-4.7** cover connections; **INV-6** names the scrubber and the *given* exception; Appendix A gains the settings above.
- ADR-0010 records the in-house egress proxy.

## Tests to write first

- Attack: a run of a role without the grant sees no secret, in its environment, its context pack or through the proxy; a run of another project of the same chairman sees none.
- Attack: through the proxy, a granted site gets the header and no other site does, even when the agent names the granted site in a header of its own (`Host` mismatch, SNI mismatch, a redirect to another host).
- Attack: an agent that prints a *given* secret in a shell, posts it, writes it to a file, puts it in evidence or memory, or sends it in a model request, leaves no copy anywhere, and the provider receives `[secret: NAME]`.
- Attack: an MCP client cannot create or replace a value, sign in, add a command server, allow a write tool or delete; it can list names.
- Attack: a denied MCP tool call never reaches the server (the test server records every request), is refused with the rule, and counts toward the refusal cap.
- Attack: an MCP URL resolving or redirecting to a private address is refused unless an admin allowed it; a metadata address is always refused; a reserved environment variable name and a collision are refused.
- Attack: a spec carrying a value is refused; an export of a project with connections carries names only.
- State machine tables and property tests for the connection item, the MCP server, the tool permission and the need.
- Contract: each auth kind against a local test MCP server, including OAuth with a local authorization server that issues short-lived tokens and rotates refresh tokens; a command server in a container (skipped without Docker).
- Scenario: start refused while a need is missing, on every surface; start without it holds exactly the dependent seats; adding it lifts the hold.
- Scenario: replacing a secret takes effect on the next request and restarts warm seats.
- The leak test of measure 3, after the exit demo.

## Risks

| Risk | Mitigation |
| --- | --- |
| The proxy is security-critical code | Small and single-purpose; tunnels everything it does not need to read; attack tests for host confusion; reviewed against the TLS and HTTP/1.1 edge cases before it is called done |
| Programs that ignore proxy settings or pin certificates | The form says so and offers *given to the agent*; stated in SECURITY.md |
| The scrubber misses an encoding | Covers the common encodings; stated as a safeguard, not a guarantee; *sent for you* is the default |
| OAuth flows differ between providers | Built on the MCP SDK's OAuth client; tested against a local authorization server and two real public MCP servers |
| Command servers run third-party code | Their own containers, no workspace, nothing of any agent's; adding one is human-only and says what it is |
| The phase is large | Nine parts, each shippable; the order puts the WordPress case (7B.0 to 7B.3) first |

## Out of scope

- Prompts and resources offered by MCP servers (tools only).
- Per-agent secrets inside a role; an external secret manager (Vault, 1Password) as a store.
- Command-line agent logins (parked separately).

## Owner's answers (23 Nov 2026)

The owner asked that each be answered by what a world-class product would do, what is right for the user, and what lasts. Recorded as decided on that basis.

1. **Where things live:** three scopes, install, person and project, with attachment and role grants; collisions refused, never shadowed. *(Changed from the first draft, which had only two.)*
2. **Private networks:** allowed per MCP server when an admin turns it on, with a warning; link-local and cloud metadata addresses always refused.
3. **Command (stdio) MCP servers:** in this phase, each in its own container. *(Changed: most useful MCP servers are commands, and a person should be able to add any of them.)*
4. **Secrets the agent never sees:** yes, as the default: the egress proxy sends a secret for the agent to the sites it is meant for. *Given to the agent* remains for what cannot be sent, masked everywhere, with its risk stated. *(Changed: safety should be the default, not an option.)*
5. **Starting with something missing:** start shows what is missing with **Add them now**; **Start without them** holds exactly the seats that need it, with the reason, until it is added. Nobody pays for runs that cannot work, and nobody is blocked from the work that can. *(Changed from a hard refusal.)*
6. **Install items:** admins only.
7. **Default grant:** the roles that declared the need; if none did, the chairman picks before attaching.
