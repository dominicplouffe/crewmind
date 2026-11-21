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
- **Agent-written text** sent to an AI client is wrapped in a labelled envelope and cannot close it (INV-7). No agent text exists yet; the envelope is in place for when it does.
- **The server binds to 127.0.0.1.** Binding elsewhere is refused without an https public URL (NFR-6). crewmind does not terminate TLS itself: put a TLS proxy in front.
- **No telemetry** leaves the install (NFR-1).

## What is not protected

- **No second factor yet.** An account is protected by its password alone. TOTP is planned after v2.0 (ACC-7). Until then, do not publish an install to the internet without another layer in front, such as a VPN or an authenticating proxy.
- **Instance admins can read every project,** and can hand a project's chair to someone else in an emergency. Both are by design and the hand-on is recorded as break-glass (section 3). Treat admin accounts accordingly.
- **The host operator can do anything.** The master key sits in the data directory beside the database, and a backup archive contains both. Protect the directory and every archive as you would the key itself.
- **Password reset links are passed on by hand** until outbound mail ships (phase 6). Whoever holds an unused link can set that person's password for 72 hours.
- **The CLI stores a personal token** in `cli.json` in the data directory, readable only by its owner. Anyone who can read that file can act as that person until the token expires or is revoked.
- **SQLite files are not encrypted.** Only secret values are encrypted at rest; project names, goals, settings and the event log are plain in the database. Use disk encryption if that matters.
- **Rate limiting** exists only for sign-in. Other endpoints are not rate limited.

## Not built yet

Each of these is specified and will be documented here when it ships.

- **What contains an agent run, and what does not.** Runs will be sandboxed in containers with a network per project. Network egress will be open by default: a run can reach the internet (EXE-14).
- **Where the model gateway does not apply.** Model calls will go through the platform gateway, so no sandbox holds a provider key. The one exception will be subscription harnesses that need a local login (LLM-8).
- **What skill scripts and the agent browser can reach** (LIB-6, EXE-17).
- **OAuth for MCP clients** (phase 6). Today MCP clients use minted bearer tokens only.

## Reporting a problem

Open a private security advisory on the repository, or write to the maintainer. Please do not open a public issue for a vulnerability.
