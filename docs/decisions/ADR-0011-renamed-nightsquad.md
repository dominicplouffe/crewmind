# ADR-0011: The project is renamed Nightsquad

- **Status:** Accepted (24 Nov 2026, owner: Dominic). Supersedes [ADR-0008](ADR-0008-project-name.md).
- **Spec:** all sections; LIB-2, SPD-9, IF-4.1 by name

## Context

"crewmind" reads as a relative of CrewAI, a large multi-agent framework. The space has also filled since ADR-0008: Paperclip is an open-source, self-hosted platform that runs a company of AI agents with a CEO agent, a board and budgets, and YokeBot is an open-source, self-hosted "AI agent workforce". Most dictionary words that fit the product (quorum, bylaw, keel, mandate, ratify, bulwark, docket and others) are already used by AI-agent or agent-governance products, several with registered software trademarks. Nightsquad had no conflict in AI or developer tools, and its PyPI and npm names were free on 24 Nov 2026. The pending NIGHTSHIFT software trademark (serial 99847649) is the nearest mark; the owner is to confirm clearance before public launch.

## Decision

- The product is **Nightsquad** in prose. The Python package, import root, PyPI and npm names are `nightsquad`.
- The CLI command is **`squad`**, with `nightsquad` installed as a second name for the same entry point. `ns` was rejected: it is not a base Linux command, but the NativeScript CLI and the ns-2 network simulator both install one. `squad` collides only with Linaro's SQUAD dashboard, a narrow audience, and `nightsquad` always works.
- Operational variables are `NIGHTSQUAD_*`; the session cookie, token prefixes (`ns_`), state root (`/var/lib/nightsquad`), Docker images, Compose database, Slack channel prefix (`#nightsquad-<project>`) and install-alias mailbox (`nightsquad+<project>@domain`) follow.
- The library concept "crew" (LIB-2) becomes **squad**, in the spec, the code, the operation catalog (`squads.*`), the event log (`squad.saved`), the database (`squads`) and the content files.
- The rename is clean, with no long-lived aliases, because v2.0 is a release candidate. Three one-time bridges carry existing installs: a migration renames the table and the stored event type; importing a file exported with an old `crewmind_*` marker still works; `squad doctor` names leftover `CREWMIND_*` variables or an old state root and how to move them. Tokens issued under the old prefix stop working, so people sign in again and MCP clients are minted new tokens.

## Consequences

History keeps the old name: the spec CHANGELOG entries before revision 2.32, ADR-0008 and the phase reports in `docs/phases/` are not rewritten. A unit test fails if the old names return anywhere else.
