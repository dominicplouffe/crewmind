# Security

This page states what crewmind protects, what it does not, and where the sharp edges are. It is a product requirement (NFR-14), kept honest as each phase ships (P12).

Status: phase 1. Agents, sandboxes, the model gateway and integrations are not built yet. Their sections say what the design requires and are marked **not built yet**.

## Trust boundaries

| Boundary | Who is on the outside | What holds it |
| --- | --- | --- |
| The server's host | Everyone but the host operator | Host-local commands (`setup`, `up`, `backup`, `restore`, `rotate-key`, `update`, `migrate`, `bootstrap-admin`, `reset-link`) have no network route (IF-4.2). Whoever has a shell on the host, and can read the data directory, controls the install |
| The human API | Anyone on the network | Every operation declares who may call it, checked before it runs (IF-3.2). A project you cannot see answers exactly like one that does not exist (INV-5) |
| The MCP endpoint | A person's AI client | The client has its own token, never the person's. It sees and calls only the tools its scopes grant; today that is the `read` scope only (IF-5.2). Human-only actions are never offered to it (IF-5.6) |
| Agent runs | AI agents (**not built yet**) | Agents will act only through the agent API, with a token for one run, one agent and one project (P3, INV-4) |

## What is protected today

- **Passwords** are hashed with Argon2id and need 12 or more characters. Unknown, deactivated and wrong-password sign-ins get the same answer after the same work. Ten failures lock an address for 15 minutes (ACC-1).
- **Sessions, tokens and links** are stored only as hashes. A token is shown once, when minted. Sessions end at sign-out, password change, 3 idle days and 14 days. Personal tokens always expire (ACC-2 to ACC-4).
- **Browser sessions** use an `HttpOnly`, `SameSite=Strict` cookie, and a write from another origin is refused (IF-3.7).
- **Secrets** are encrypted with AES-256-GCM under the install master key. Without the key the server stores and reads no secret. Rotation is all or nothing (ACC-6).
- **The event log** records every state change with its actor, including actions taken through an MCP client, which are marked as such (INV-21, IF-5.4).
- **Agent-written text** sent to an AI client is wrapped in a labelled envelope and cannot close it (INV-7). In the web app it is rendered as sanitised markdown, and an HTML file an agent wrote is previewed only in a sandboxed frame with no scripts and no network (ART-4).
- **Provider keys never enter a sandbox.** Every model call and web search goes through the server's model gateway, which holds the key. A run carries only a short-lived run token that ends with the run (P3, LLM-8, INV-6).
- **Token budgets are enforced by the server.** At the budget wall nothing new starts; each run also has its own cap (GOV-3, GOV-6).
- **The web app** is served with a content security policy that allows no outside host, no inline script and no framing (NFR-14).
- **Work is checked by something other than the doer.** A task with a command test is done only when the platform's own run of the pinned command exits 0. The check runs in a copy of the workspace with the pinned test files restored, and with no model, no token and no key in its environment (WRK-5, WRK-7, INV-2).
- **Pages fetched for agents go through a guard.** Evidence and watch URLs are fetched only from public addresses, over http or https, with every connection and redirect re-checked, and with size and time limits. Loopback, private and cloud-metadata addresses are never reached (WRK-12).
- **Scope, dates and the budget cannot be argued with.** A task must serve an accepted requirement or an active bet. Only the platform writes a requirement met, on its own run of the test, a reviewer's verdict or its own reading of a metric. A commitment has no date field an agent can fill: its date is the platform's projection or the chairman's. The CEO reserve is drawn once, only when the platform's arithmetic says the project is nearly done, and the chairman can cancel it. What the CEO may do alone follows the project's `authority.*` settings, and it never changes a requirement the chairman wrote (PLN-1, PLN-6, PLN-10, GOV-10, INV-18).
- **Metric requirements are read through the same guard** as evidence and watches: a public page only, read by the platform, never by an agent (PLN-11).
- **Recall memory stays on your machine.** Facts are embedded by a local model that is read from disk; nothing is fetched at run time and the memory library's telemetry is switched off. An agent reads only its own, its team's and its project's memory and the chairman's preferences (MEM-2, MEM-3).
- **Push alerts** are sent only to the push services of the major browsers, over https. The alert text is encrypted for the browser; the push service sees that an alert was sent, not what it says (CHAT-20).
- **The server binds to 127.0.0.1.** Binding elsewhere is refused without an https public URL (NFR-6). crewmind does not terminate TLS itself: put a TLS proxy in front.
- **No telemetry** leaves the install (NFR-1).

## What is not protected

- **No second factor yet.** An account is protected by its password alone. TOTP is planned after v2.0 (ACC-7). Until then, do not publish an install to the internet without another layer in front, such as a VPN or an authenticating proxy.
- **Instance admins can read every project,** and can hand a project's chair to someone else in an emergency. Both are by design and the hand-on is recorded as break-glass (section 3). Treat admin accounts accordingly.
- **The host operator can do anything.** The master key sits in the data directory beside the database, and a backup archive contains both. Protect the directory and every archive as you would the key itself.
- **Password reset links are passed on by hand** until outbound mail ships (phase 6). Whoever holds an unused link can set that person's password for 72 hours.
- **The CLI stores a personal token** in `cli.json` in the data directory, readable only by its owner. Anyone who can read that file can act as that person until the token expires or is revoked.
- **SQLite files are not encrypted.** Only secret values are encrypted at rest; project names, goals, settings and the event log are plain in the database. Use disk encryption if that matters.
- **Memory is not encrypted at rest.** Remembered facts, pinned orders and decisions are plain in the database and in the `memory` folder of the data directory. To build memories, the text of finished runs is sent to the model provider that pays the project, like any other model call. Forgetting an entry deletes it from the store, the index and the history file; it does not reach back into old backups.
- **A requirement's command test runs like any other check.** It is a command the CEO or the chairman wrote, run by the platform in a copy of the workspace; in `unisolated` mode it is contained no better than an agent (see below).
- **Rate limiting** exists only for sign-in. Other endpoints are not rate limited.
- **What contains an agent run.** In `container` mode each run is a container with CPU and memory limits, the project's workspace mounted, and no install secret. Network egress is open by default: a run can reach the internet (EXE-14). The container mode has not yet been verified on a real Docker host; treat it as untested until the phase 2 notes in `docs/phases/phase-2-plan.md` say otherwise.
- **A check in `unisolated` mode is contained no better than an agent.** It is a plain process of the server's user with a clean environment, a memory limit and a timeout. A command an agent wrote can still read whatever that user can read. On such a host that also holds a container-runtime socket, agent-written checks are refused unless the operator allows them. The container version of the check has not yet run on a real Docker host.
- **`unisolated` mode contains nothing.** A run is a plain process of the server's user with a clean environment. It can read whatever that user can read, including the data directory and the master key. Use it for development on the mock provider only.
- **Subscription logins** (phase 8) will be the one exception to "no provider credential in a sandbox", because those harnesses need a local login (LLM-8). They are not built.

## Not built yet

Each of these is specified and will be documented here when it ships.

- **What skill scripts and the agent browser can reach** (LIB-6, EXE-17).
- **OAuth for MCP clients** (phase 6). Today MCP clients use minted bearer tokens only.

## Reporting a problem

Open a private security advisory on the repository, or write to the maintainer. Please do not open a public issue for a vulnerability.
