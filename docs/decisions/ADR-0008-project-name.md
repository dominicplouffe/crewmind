# ADR-0008: The project is named crewmind

- **Status:** Accepted (21 Nov 2026, owner: Dominic)
- **Spec:** all sections (formerly "yaaf")

## Context

The rebuild needed an open-source name. The owner chose crewmind.

## Decision

The product, Python package, CLI command and environment-variable prefix are `crewmind` (`CREWMIND_API`, `CREWMIND_TOKEN`). The Slack channel prefix is `#crewmind-<project>`, and the install-alias mailbox is `crewmind+<project>@domain`.

## Consequences

"Crew" is closely associated with CrewAI, a large multi-agent framework, and a small project already uses crewmind.org. README and docs should describe crewmind on its own terms (a governed AI company with a chairman and CEO) and never imply an affiliation with CrewAI. Secure the PyPI name, the GitHub organisation and the domains early.
