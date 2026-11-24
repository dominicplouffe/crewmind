# Nightsquad: Requirements & Specification (revision 2, 21 Nov 2026)

Revision 2 rebuilds Nightsquad chat-first, budgeted in tokens and built for speed. You talk to a project like a coding assistant, it stays inside the token budget you set, and Deliver ships a first usable version early.

Owner: Dominic. Requirement ids are stable; cite them in code, tests and commits.

## Reading order

Always read first:

1. [00-how-to-use.md](00-how-to-use.md): conventions, order of authority, what changed
2. [02-principles.md](02-principles.md): P1–P18, which override everything
3. [08-invariants-INV.md](08-invariants-INV.md): what must hold under any sequence of calls

Then, as the current phase needs:

| File | Contents | Ids |
| --- | --- | --- |
| [01-purpose.md](01-purpose.md) | Problem, users, experience targets, v1 frustrations mapped to mechanisms | |
| [03-actors-and-authority.md](03-actors-and-authority.md) | Actors, org shapes, the authority dial | |
| [04-domain-concepts.md](04-domain-concepts.md) | The vocabulary: one name per concept | |
| [05-chat.md](05-chat.md) | The project chat | CHAT |
| [06-functional-requirements.md](06-functional-requirements.md) | Intro to section 6 | |
| [06-01-projects-PRJ.md](06-01-projects-PRJ.md) | Project types and lifecycle | PRJ |
| [06-02-speed-SPD.md](06-02-speed-SPD.md) | Speed | SPD |
| [06-03-models-LLM.md](06-03-models-LLM.md) | Providers, gateway, quality dial | LLM |
| [06-04-budget-GOV.md](06-04-budget-GOV.md) | Token budget, CEO reserve, guards, real-world spend | GOV |
| [06-05-planning-PLN.md](06-05-planning-PLN.md) | Requirements, projection, commitments | PLN |
| [06-06-work-WRK.md](06-06-work-WRK.md) | Tasks, tests, verification, watches | WRK |
| [06-07-artifacts-ART.md](06-07-artifacts-ART.md) | Files and deliverables | ART |
| [06-08-conversation-MSG.md](06-08-conversation-MSG.md) | Channels, directives, standing orders | MSG |
| [06-09-decisions-HUM.md](06-09-decisions-HUM.md) | Decision items, flags, reporting | HUM |
| [06-10-execution-EXE.md](06-10-execution-EXE.md) | Wakes, runs, sandboxes, browser | EXE |
| [06-11-memory-MEM.md](06-11-memory-MEM.md) | Pinned and recall memory | MEM |
| [06-12-founder-FND.md](06-12-founder-FND.md) | Drafting and grilling | FND |
| [06-13-rehearsal-RHS.md](06-13-rehearsal-RHS.md) | The zero-token fire drill | RHS |
| [06-14-library-LIB.md](06-14-library-LIB.md) | Roles, squads, specs, Agent Skills | LIB |
| [06-15-integrations-INT.md](06-15-integrations-INT.md) | Webhooks, data sources, Slack, email, A2A | INT |
| [06-16-accounts-ACC.md](06-16-accounts-ACC.md) | Accounts and access | ACC |
| [06-17-connections-CON.md](06-17-connections-CON.md) | Secrets, variables and MCP servers | CON |
| [07-state-machines.md](07-state-machines.md) | Every lifecycle, as transition tables | |
| [09-interfaces-IF.md](09-interfaces-IF.md) | Catalog, API, CLI, MCP, agent API, parity | IF |
| [10-background-BG.md](10-background-BG.md) | Jobs and processes | BG |
| [11-nfr-NFR.md](11-nfr-NFR.md) | Non-functional: operations, security, slim mode, stack | NFR |
| [12-lessons-from-v1.md](12-lessons-from-v1.md) | What the rebuild must design out | |
| [13-acceptance-and-build-order.md](13-acceptance-and-build-order.md) | Acceptance criteria, build order | |
| [14-open-questions.md](14-open-questions.md) | Owner decisions still open | |
| [appendix-a-settings.md](appendix-a-settings.md) | Every setting: default, range, scope | |

Changes to the spec are logged in [CHANGELOG.md](CHANGELOG.md).
