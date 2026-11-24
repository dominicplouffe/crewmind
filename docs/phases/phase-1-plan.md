# Phase 1 plan: core

Goal (PLAN.md): projects exist, are governed by versioned settings, and are reachable from the API, the CLI and MCP (read).

**Exit demo.** In slim mode (`squad up --slim`) and on a Postgres server: create a user and a project, change a setting with a reason, then start, hold and resume the project. See every change in the event log from the CLI, the API and an MCP client.

Status: **agreed with the owner on 21 Nov 2026.** The answers are at the end.

## How a call is carried out

Phase 0 handlers take only an input. Phase 1 gives every operation one path, shared by all surfaces, so no surface can skip a step:

1. **Authenticate** (surface): turn a session cookie, a personal token or an MCP token into a caller. A caller is a person, plus how they came in: directly, or through a named MCP client (INV-21, IF-5.4).
2. **Authorize** (catalog): check the operation's declared authority against the caller, before the handler runs (IF-3.2, NFR-11). An operation with no declared authority cannot be registered.
3. **Resolve the project**: any operation that names a project goes through one lookup. A project the caller cannot see answers exactly as one that does not exist (INV-5, IF-3.3).
4. **Idempotency**: a write with a key already seen returns the stored result (IF-3.5).
5. **Run the handler in one transaction**: state change and its event are written together (NFR-10, INV-21).

Authorities an operation can declare: `anyone` (login only), `person`, `admin`, `project_observer`, `project_chair` (chairman or co-chair), `project_chairman_only`, `host_operator`.

## Modules

```
src/nightsquad/
  catalog/
    execute.py        The five steps above; the only way a handler is called
    caller.py         Caller, authorities, the via field
    state_machine.py  Table-driven machine: declared transitions, everything else refused
  domain/
    accounts/         People, passwords, lockout, sessions, tokens, links, membership (ACC-1 to ACC-5)
    secrets/          Master key, encryption at rest, rotation (ACC-6, NFR-12)
    projects/         Project, lifecycle, hold reasons, start checks, stop and purge hooks (PRJ-1, 2, 3, 10)
    settings/         service.py: effective values, changes with a reason, versions, constraints (GOV-1)
    record/           The event log: typed events, append, read (INV-21)
    install/          Host-local operations: setup, up, doctor, backup, restore, rotate key, update, migrate
  surfaces/
    api/auth.py       Cookies, bearer tokens, cross-origin write protection (IF-3.7)
    mcp/              Streamable HTTP endpoint, bearer auth, read scope, untrusted-text envelope (INV-7)
    cli/              Login state, hidden input for secrets (IF-4.5)
  jobs/               Scheduler loop and the phase 1 jobs (BG-1, BG-3, BG-4)
  storage/models/     One file per domain
  server.py           The app `squad up` runs: API, MCP and scheduler; full or slim (NFR-23)
```

`domain/record` and `jobs/` are additions to the layout in CLAUDE.md, which will be updated.

## Tables

| Table | Holds | Notes |
| --- | --- | --- |
| `persons` | Email, name, instance role, state (7.8), password hash | Argon2id (ACC-1) |
| `login_attempts` | Failures per address, known or not | 10 failures lock for 15 minutes (ACC-1) |
| `sessions` | Hash of the session id, person, created, last seen, ended | 14 days at most, 3 idle days (ACC-2) |
| `tokens` | Hash, kind (personal or MCP), name, scopes, MCP client name, expiry, state (7.10) | Never the token itself (ACC-3, NFR-12) |
| `links` | Hash, kind (invite or reset), person, state (7.9), expiry | Single use, 72 hours (ACC-4) |
| `projects` | Name, type, goal, state (7.1), state before deleting, delete time, registry version | Type never changes (PRJ) |
| `project_hold_reasons` | Project, reason, lift time, added and lifted times | The hold-reason set of 7.1 |
| `memberships` | Project, person, role, state (7.11) | Exactly one chairman per project, enforced by a unique index |
| `setting_values` | Scope, subject (project, person or install), name, value, version, reason, actor, time | Append-only; the newest version is the value (GOV-1) |
| `events` | Sequence, project (empty for install events), type, actor, via, time, before, after | Append-only; written in the same transaction as the change |
| `idempotency_keys` | Caller, operation, key, stored result | IF-3.5 |
| `secrets` | Name, owner, ciphertext, key version | Built and tested now; first used by model credentials in phase 2 (ACC-6) |

## Operations

All are catalog operations; the API, CLI and MCP adapters are generated. MCP gets only the read operations marked ◆ (IF-5.2 `read` scope).

| Group | Operations | Authority |
| --- | --- | --- |
| `auth` | `login`, `logout`, `whoami` ◆, `change_password`, `use_link` (set a password from an invite or reset link) | `anyone` for `login` and `use_link`; `person` otherwise |
| `people` | `invite`, `list`, `set_role`, `deactivate`, `reactivate`, `reset_link` | `admin` |
| `tokens` | `mint`, `list`, `revoke` | `person` |
| `mcp_clients` | `mint` (with scopes; `read` only for now), `list`, `revoke` | `person`; never on MCP (human-only) |
| `projects` | `create`, `list` ◆, `status` ◆ | `person`; `project_observer` for `status` |
| `projects` | `start`, `hold`, `resume`, `stop` | `project_chair` |
| `projects` | `delete`, `confirm_delete`, `cancel_delete` | `project_chairman_only`; never on MCP (IF-5.6) |
| `members` | `list` ◆, `add`, `set_role`, `remove` | `project_observer` to list; `project_chair` to change; changes never on MCP (IF-5.6) |
| `members` | `hand_on_chair`; `break_glass_hand_on` | `project_chairman_only`; `admin` |
| `settings` | `show` ◆, `history` ◆, `registry` ◆, `change` (a bundle, with a reason) | By scope (GOV-1) |
| `record` | `list` ◆ (cursor-paginated, filter by time and project) | `project_observer`; `admin` for install events |
| `install` (host-local, top-level commands) | `setup`, `up`, `doctor`, `backup`, `restore`, `rotate_key`, `update`, `migrate`, `bootstrap_admin`, `reset_link` | `host_operator` |

Health endpoints (`/healthz`, `/readyz`, NFR-5) are infrastructure routes outside `/v1`, not operations.

## Rules and their attack tests

Each rule is registered with its id, and each has an attack test through the public API (P10).

| Rule | Attack |
| --- | --- |
| INV-5 invisible means nonexistent | For every operation that names a project: a non-member's answer is byte-identical to the answer for a random id. The test walks the catalog, so new operations are covered automatically |
| IF-3.2 every route declares who may call | Walk every route with no credential, a revoked token, an expired token and a deactivated person's token: all refused before the handler |
| ACC-1 passwords and lockout | Unknown, deactivated and wrong-password logins return the same body and take the same time within a tolerance; the 11th attempt is locked out even with the right password |
| ACC-2, IF-3.7 sessions | A session works after sign-out or password change: refused. A cross-origin write with a valid cookie: refused |
| ACC-3 tokens | A token past its expiry, a request for a non-expiring token, a token read back from the API: all refused or absent |
| ACC-4 links | A link used twice, or after 72 hours: refused |
| ACC-5 membership | A removed member's next request; a co-chair deleting or handing on the chair; an observer writing; a second chairman: all refused |
| IF-5.2, IF-5.6 MCP | A read-scope MCP token calling any write, or any human-only operation: answered as an unknown tool |
| GOV-1 settings | No reason, a 9-character reason, an unknown name, an out-of-range value, a bundle breaking a constraint, a member changing an install setting: all refused, and a refused bundle changes nothing |
| Section 7 transitions | Every transition not in the 7.1 and 7.8 to 7.11 tables is refused, for every actor |
| PRJ-2 resume at the wall | `/resume` while `budget_wall` holds is refused with the arithmetic. The wall cannot occur until phase 2, so the test adds the reason directly |
| PRJ-10 delete | One-step delete; delete by a co-chair; delete through MCP; purge before the grace ends: all refused |
| INV-6 secrets | No operation output field can carry a secret: a test walks every output schema. Secret values never appear in logs or events |

## Tests to write first

- **State machines** (CLAUDE.md): table-driven tests for 7.1 and 7.8 to 7.11, plus Hypothesis tests. For projects: under any sequence of holds, lifts, resumes and stops, the state always equals what the hold-reason set implies, and no unlisted transition is ever taken.
- **Spec drift:** a test parses the From and To columns of the section 7 tables and compares them with the declared machines, as phase 0 does for settings.
- **Event log** (INV-21): every operation of class `reversible` or `irreversible` writes at least one event with actor, via, time, before and after. The test walks the catalog.
- **Same transaction** (NFR-10): a handler that fails after changing state leaves neither the change nor the event.
- **Background jobs** (BG-1, BG-3, BG-4): each job run twice changes nothing the second time; a project whose job raises does not stop the others; each automatic change names its job as actor.
- **Chaos** (NFR-9): drop every pooled connection, then the API and the scheduler recover without a restart.
- **Slim and move up** (NFR-23): the exit demo runs in one process on SQLite; `squad migrate --to postgres` then shows the same projects, settings and events on Postgres. Start time and idle memory are measured against 5 seconds and 400 MB.
- **Backup and restore** (NFR-4), **key rotation** (ACC-6: a failure part-way changes nothing), **bind rules** (NFR-6: a non-local bind without TLS and a public URL is refused).
- **Exit demo as a scenario test**, on both databases, through the CLI, the API and an MCP client.

## Decisions this plan makes

| Topic | Choice |
| --- | --- |
| Password hashing | Argon2id (`argon2-cffi`). Every login runs one hash check, even for unknown addresses, so timing does not leak (ACC-1) |
| Tokens and sessions | Random 256-bit values with a prefix (`cm_pat_`, `cm_mcp_`), stored as SHA-256 hashes |
| Encryption at rest | AES-256-GCM (`cryptography`), key version stored per value so rotation can be checked (ACC-6) |
| Cross-origin writes | `SameSite=Strict` session cookie, plus an Origin check on every write (IF-3.7) |
| Two-step delete | `projects.delete` returns a single-use confirmation; `projects.confirm_delete` needs it and the project's name typed. The export offer arrives with exports in phase 7 |
| Events | One table for project and install events. Admins read install events |
| Platform hold reasons | The mechanism is built and tested now. Nothing in phase 1 can add `budget_wall`, `auth_failures` or `skipped_cycles`; phases 2 and 5 add the triggers |
| Scheduler jobs in phase 1 | Lift chairman holds at their lift time; purge projects after `delete.grace`; expire links, sessions and tokens |
| NFR-16 (idle costs nothing) | Nothing in phase 1 can spend tokens. Marked "not yet exercised" in the matrix, not "done" |

## Suggested order

Four increments, each ending with the full suite green on both databases:

1. **Call path and accounts:** execute path, callers, state-machine base, event log, people, login, sessions, tokens, links.
2. **Projects:** create, lifecycle with hold reasons, membership, settings service, scheduler jobs.
3. **MCP read:** HTTP endpoint, MCP tokens, read scope, untrusted-text envelope.
4. **Install:** `up` (slim and full), setup, doctor, backup, restore, key rotation, migrate, update, SECURITY.md, the exit demo.

## Owner answers (21 Nov 2026)

| Question | Answer |
| --- | --- |
| Setup links with no web app | The CLI accepts them in phase 1: `squad accept <link>` asks for a password with hidden input (operation `auth.use_link`). The same link opens a web page from phase 2. No web code in phase 1 |
| Password resets with no outbound mail | An admin issues a reset link (`people.reset_link`), or the host operator does on the server. Self-service reset by email arrives with outbound mail in phase 6 |
| Deactivating a person who chairs a project | Refused, naming the projects they chair. The admin hands each chair on first (break-glass, recorded). Added to ACC-5 and 7.8 (spec revision 2.4) |
| INV-4 and BG-2 | Both move to phase 2, where runs and the dispatcher exist |
| Full-server packaging | A Docker Compose bundle (Postgres with pgvector, plus the server) that `squad setup` can start, and support for a Postgres the owner already runs. Slim mode needs neither |
| Update | Source checkouts only, as NFR-3 specifies. A tool install is told to run `uv tool upgrade`; `squad up` then migrates on start. Revisit when a package is published |
| Review points | One stop, at the exit demo. The four increments are still built in order, each with the suite green on both databases |

No open questions remain.

## Outcome (21 Nov 2026)

Built as planned, in the four increments. 53 operations, 12 tables, 24 registered rules, each with an attack test. The suite passes on SQLite and on Postgres.

Differences from this plan:

- **Setup links:** the command is `squad accept --link <link>`, with the link as an option, not a bare argument.
- **Compose bundle:** `deploy/deploy_single_server.sh` builds and starts it (22 Nov 2026): Postgres, the server, a TLS front, and the agent image. It was run end to end once by hand on Docker 29, with a browser sign-in on a non-localhost address and a scripted agent answering from a container. No automated test starts the bundle.
- **Update:** the refusals (dirty checkout, package install) and the dry run are tested. The pull, sync and restart path has not been run for real.
- **First admin:** created as invited with a setup link, not directly active. Section 7.8 was corrected (spec revision 2.5).
- **Break-glass hand-on** may name a person who is not yet a member; they join as a co-chair first. Section 7.11 was extended (spec revision 2.5).
- **GOV-1** (a phase 2 id) is built here, because phase 1 needs the settings service. Disclosure to the CEO still waits for phase 2.
- **Operations split by scope:** `settings.change` became `change_project`, `change_mine` and `change_install`, and `record.list` gained `record.list_install`, because each needs a different authority.
