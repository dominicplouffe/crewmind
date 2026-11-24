# ADR-0008: The project is named nightsquad

- **Status:** Accepted (24 Nov 2026, owner: Dominic)
- **Spec:** all sections; IF-4.1 for the command

## Context

The rebuild needed an open-source name that stands apart from the multi-agent tools around it: CrewAI, a large multi-agent framework; Paperclip, an open-source, self-hosted platform that runs a company of AI agents with a CEO agent, a board and budgets; and YokeBot, an open-source, self-hosted "AI agent workforce". Most dictionary words that fit the product (quorum, bylaw, keel, mandate, ratify, bulwark, docket and others) are already used by AI-agent or agent-governance products, several with registered software trademarks. nightsquad had no conflict in AI or developer tools, and its PyPI and npm names were free on 24 Nov 2026. The pending NIGHTSHIFT software trademark (serial 99847649) is the nearest mark; the owner is to confirm clearance before public launch.

## Decision

- The product name is **nightsquad**, in lower case everywhere, as the brand guide (`docs/design/brand.md`) keeps it. The Python package, import root, PyPI and npm names are `nightsquad`.
- The CLI command is **`squad`**, with `nightsquad` installed as a second name for the same entry point. `ns` was rejected: it is not a base Linux command, but the NativeScript CLI and the ns-2 network simulator both install one. `squad` collides only with Linaro's SQUAD dashboard, a narrow audience, and `nightsquad` always works.
- Operational variables are `NIGHTSQUAD_*` (`NIGHTSQUAD_API`, `NIGHTSQUAD_TOKEN`). Tokens start with `ns_`. The server's state root is `/var/lib/nightsquad`, the Slack channel prefix is `#nightsquad-<project>`, and the install-alias mailbox is `nightsquad+<project>@domain`.
- The library's ready-made job with a team already on it (LIB-2) is a **squad**.

## Consequences

README and docs describe nightsquad on its own terms (a governed AI company with a chairman and CEO) and never imply an affiliation with another product. Secure the PyPI and npm names, the GitHub organisation and the domains early. A unit test fails if a name used before this decision appears in the repository again.
