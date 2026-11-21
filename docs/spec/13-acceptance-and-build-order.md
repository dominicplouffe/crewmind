## 13. Acceptance criteria and build order

The rebuild is acceptable when all of the following pass on a clean install. Reference specs for the scenarios ship in the repository's `acceptance/` folder: one each for Explore, Deliver and Operate, plus a raw one-paragraph brief and a reference goal with its hand-graded grammar.

- **Golden path, each type.** Each reference spec, run by the scripted crew, gets from creation to its first verified close with no human input beyond what its authority settings require.
  - Deliver claims its first task within 10 minutes, publishes a first usable version, passes its final gap review, reaches ready and writes a receipt.
  - Explore ends its bets with findings and produces a findings report.
  - Operate rolls two cycles with scorecards.
- **Rule-breaker.** A scripted agent tries every forbidden action in INV-1 to INV-7 and INV-23. It is refused each time, hits the refusal cap, and has its token revoked. No forbidden state is reached.
- **Listening.** The frustration scenarios in NFR-19 all pass. Standing orders, decisions, corrections and examples reach every relevant context pack verbatim (INV-25), and the memory eval suite meets MEM-8.
- **Never silent.** With the provider down, the budget at the wall, the project held, and a crash mid-reply, every chairman message gets a reply or a platform status within 60 seconds (INV-24).
- **Losing.** A scripted CEO that stays quiet while a metric moves away from target fails the floors: a losing-ground flag opens and must be raised.
- **Speed.** The Deliver reference spec with concurrency 4 completes in no more than 1.3 × (its longest dependency chain × median scripted run duration). No ready task waits more than 10 seconds for a lease when limits allow.
- **Chaos.** Killing runners mid-run, dropping database connections and racing runners violate none of INV-8 to INV-16.
- **Surface parity.** The conformance test (IF-1.3) passes. A person can create, steer, inspect and configure a project end to end four ways: only the app chat, only the CLI (including `crewmind chat`), only an MCP client with the four scopes, and (for the Slack column of the parity matrix in section 9.8) only Slack.
- **Multi-provider.** The same project runs seats on at least three providers, including one local OpenAI-compatible model, and one subscription credential. The ledger shows each provider's tokens against the one budget. No sandbox ever holds a provider key, except the stated subscription-harness exception.
- **Founder.** The reference goal grades ready. The raw brief does not, and is missing exactly the elements the hand-graded reference names. Quick mode creates and starts a project in under 2 minutes. A reference document seeded with two contradictions, one illustrative number and one requirement nobody can verify yields a question on each, one at a time, before any draft (FND-15). The same document grilled in a running project also surfaces its planted conflict with a standing order (FND-16).
- **Budget.** At the wall with no eligible reserve, the project pauses within one scheduler tick, nothing new is leased, in-flight runs finish within `run.max_tokens`, and the overspend is no more than the in-flight runs (INV-9). At 90%, new scope is refused and the budget checkpoint opens. A Deliver project that is 80% done reaches the wall, draws the CEO reserve instead of pausing, tells the chairman, and completes within budget plus reserve. A project only 50% done has its draw refused.
- **Experience.** The section 1.3 targets are met on the reference hardware. An automated accessibility audit of the app reports no WCAG 2.2 AA violations.
- **Standards.**
  - A role granted a public skill loads only its description until it activates the skill, then uses it. A skill whose script asks for a credential the role lacks is refused.
  - A scripted agent signs in to a local test site with a role credential, and the value appears in no trace or span. A payment form submitted without an open purchase is refused.
  - Traces from a golden-path run arrive at a test OpenTelemetry collector with no secret value and no content unless capture is on.
  - A test A2A agent on the allowlist sends a task, which arrives as a suggestion. A call from, or to, an agent not on the allowlist is refused.
- **Slim.** The Deliver golden path passes in slim mode on SQLite. The same project, moved with `crewmind migrate --to postgres`, continues on a full server with nothing lost.

**Build order.** Each phase ends shippable and tested.

1. **Core.** Operation catalog and adapters (API, CLI, MCP read scope); accounts, membership and tokens; event log; settings registry; projects and lifecycle (section 7.1); both databases and slim mode from the first commit.
2. **Chat and execution.** Project chat (app and `crewmind chat`) with streaming, slash commands, uploads and artifacts; model gateway with metering; harness interface with the mock and one real harness; one container sandbox; dispatcher, leasing, heartbeats and reaping; agent API (context, tasks, messages); token budget and the wall.
3. **Listening.** Pinned memory, standing orders, decisions, corrections, examples and directives; recall memory on Mem0 (pgvector, or an embedded store on SQLite); the communication lint.
4. **Verification.** Success tests with red-first and pinned files; platform checks; independent read; figures basis; final gap review; outside evidence; side effects and watches.
5. **Planning and speed.** Requirements and readiness; throughput and projection; commitments (Deliver); bets and time boxes (Explore); cycles (Operate); speed flags and time attribution.
6. **Chairman loop.** Decision items, desk, daily brief, since-you-were-away, agenda, status reviews, alerts; steer and create MCP scopes; two-phase confirmation.
7. **Founder and rehearsal.** Goal grammar grader, drafting in chat, quick mode, specs, role and crew libraries; Agent Skills.
8. **Breadth.** More providers and harnesses, lineup overrides, circuit breakers; data-source gateway; configure scope and OAuth; webhooks; Slack channel bridge; email; agent browser; A2A; OpenTelemetry export; desktop install.
