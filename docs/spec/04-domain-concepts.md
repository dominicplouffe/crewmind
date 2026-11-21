## 4. Domain concepts

This is the rebuild's whole vocabulary. Each concept has one name, used in the code, the API and the UI alike. The one exception is the product words chairman, CEO and project chat, which may appear in UI copy. Storage design is up to the implementer. Lifecycles are in section 7.

| Concept | What it is | Key facts |
| --- | --- | --- |
| **Project** | One goal pursued by one org under one rule set | Has a **type** (Explore, Deliver or Operate) fixed at creation, a lifecycle state, a brief, settings, a roster, a ledger, a workspace and a chat |
| **Goal** | Prose describing the outcome, written for the CEO | Graded against the goal grammar (FND-7). At most 6,000 characters. Chairman-owned (P7) |
| **Brief** | The goal plus active standing orders | In every run of every agent |
| **Standing order** | A chairman instruction that holds until retired | One sentence, 400 characters or fewer, at most 25 active. Created by pinning (MSG-4). Retired orders stay visible as retired |
| **Decision** | A closed topic: what was decided, by whom, when | Created by `/decide` (MSG-5). In every run. Reopened only by the chairman, or by a request citing newer evidence |
| **Correction** | The chairman's "not what I asked" on an agent message | Stored with the chairman's words; pinned for the agent concerned (MSG-6) |
| **Example** | Text the chairman marked as illustrative | Never used as data; labelled ILLUSTRATION in every context pack (MSG-7) |
| **Directive** | An explicit instruction to act | Made by `/do` or by accepting an action card. The only way chat words change state (P15) |
| **Action card** | An agent's proposal to act on something said in chat | Do it / Not now / Edit. "Do it" creates a directive |
| **Settings** | Every governed number and switch for a project | Versioned, append-only, reason required, effective at once, disclosed to the CEO. Registry in Appendix A |
| **Quality** | The single model-and-effort dial | `fast`, `balanced` or `best` (LLM-3) |
| **Budget** | The project's token allowance | Total for Explore and Deliver, per month for Operate. The budget is the wall (GOV-3) |
| **Role** | A versioned agent template | LIB-1 |
| **Team** | Seats created from one pinned role version | Has a derived lead. Can be stood down and recalled with its history intact |
| **Seat** (agent) | One working identity in a project | Kind: CEO, lead, worker or reviewer. Status: active, paused or stood down |
| **Requirement** | Something that must be true by the end | One-off or recurring (Operate). Has an acceptance test, an estimate in runs (the first estimate is kept forever), an author (chairman or CEO), an optional stage, and dependencies (no cycles) |
| **Bet** | Explore's unit of scope | A hypothesis with a kill condition and a kill date. Ends confirmed, killed or inconclusive, with a written finding |
| **Commitment** | A Deliver project's delivery date | Computed by the platform from throughput; no agent writes a date |
| **Cycle** | One period of an Operate project | Hourly to quarterly. At most one open. Closes as completed, missed or skipped, with a scorecard |
| **Task** | A unit of work | Serves a requirement (Deliver, Operate) or a bet (Explore). One level of subtasks |
| **Success test** | How "done" is decided | **Command:** the platform runs it. **Observable:** names an artifact, URL or measurement a reviewer checks. **Metric:** a reading from outside the project (requirements only) |
| **Evidence** | A claim that something happened outside the project | Pending until the platform verifies it; signed webhooks are platform-attested |
| **Artifact** | Any file in the project | Versioned with a content hash. Kinds: deliverable, working, upload, report (section 6.7) |
| **Deliverable** | An artifact published as output for the chairman or outside readers | One canonical deliverable per purpose; superseded versions fold away |
| **Workspace** | The project's shared working files | Mounted into every run and check; every file is visible as a working artifact |
| **Watch** | A recurring platform check on something launched outside | Required for every launch side effect (WRK-17). Runs at 0 tokens |
| **Project chat** | The project's front door | Chairman, co-chairs, observers (read-only), the CEO and any addressed agent (section 5) |
| **Channel** | A conversation space | Project chat, leadership (CEO and leads), one room per team |
| **Notice** | A platform message to an agent | Consumed on read; urgent kinds wake the agent (EXE-2) |
| **Suggestion** | An agent's idea for the backlog | Creates no work; handed to the CEO's next planning run |
| **Memory** | What agents keep between runs | Pinned layer (exact) and recall layer (searched); section 6.11 |
| **Decision item** | Anything waiting on a human | One type with kinds (HUM-2). Each has a recommendation, a deadline, a default outcome, typed actions and a history |
| **Flag** | A decision item opened by arithmetic, never by agent judgement | HUM-6 |
| **Run** | One sandboxed agent execution | Kinds: work, chat, check. Metered, traced, one run token |
| **Ledger** | Every metered line | Tokens for model use (by kind: input, output, cache write, cache read); money for real-world spend and revenue; counts for searches. Every line carries its unit |
| **Side effect** | An action with consequences outside the platform | Two-phase (declare, then finish) with an idempotency key. Launch side effects carry a watch |
| **Credential** | A stored secret | Model credential (pays seats, used only by the gateway), role credential, data-source credential, mailbox (managed or manual, INT-6), mail-server admin key, webhook secret. Encrypted; has a health status |
| **Model gateway** | The platform service every model call passes through | Adds the provider credential, meters tokens, enforces the per-run cap |
| **Data source** | An outside MCP server the chairman connected | Reached only through the platform gateway; per-tool permissions |
| **Event log** | Append-only record of every state change | The single source for audit, briefs, agenda, feeds, notifications and mirrors |
| **Mail server** | An install-level connection to a mail server the platform can create mailboxes on | Stalwart first, through a provisioning adapter (INT-6). Its admin key is used only by the mail provisioner |
| **Skill** | A packaged capability in the open Agent Skills format | Versioned; reviewed before use; pinned by roles; loaded on demand (LIB-6) |
| **External agent** | An agent outside the project, reached by email or A2A | Only if on the chairman's allowlist; its messages are material, never orders (INT-10, INT-11) |
