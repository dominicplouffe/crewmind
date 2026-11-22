### 6.3 Models and quality (LLM)

crewmind is provider-neutral. The chairman chooses **who pays** and a **quality** level; the platform chooses models and effort. Nobody has to pick a model or an effort level unless they open Advanced.

- **LLM-1 Providers through one gateway.**
  - Every model call passes through the platform's model gateway.
  - The provider registry is data, not code. The minimum set: Anthropic, OpenAI, Google Gemini, Google Vertex AI, Azure OpenAI, AWS Bedrock, Mistral, DeepSeek, and any OpenAI-compatible endpoint (covering OpenRouter, Groq, Together, Fireworks, xAI, Ollama, LM Studio and others).
  - The gateway SHOULD be built on an established open-source gateway (LiteLLM is the reference candidate) rather than hand-written provider adapters.
  - For each provider the registry records its credential shape, whether it searches natively, whether it supports images, and its default harness.
- **LLM-2 Model credentials.**
  - Stored encrypted; listed by name only, never by value; can be hidden without being deleted.
  - Two kinds: **API key** and **subscription login**. Both are metered in tokens.
  - For subscription logins the system shows remaining plan usage (rolling windows) from rate-limit signals already reported, without polling. Whether a provider's terms allow this use is the user's decision; crewmind neither blocks nor warns.
- **LLM-3 The quality dial.** One project setting, `quality` \[balanced\], decides model class and effort for every seat by the seat's kind:

| Quality | Thinking seats (CEO, leads, reviewers) | Doing seats (workers) |
| --- | --- | --- |
| fast | balanced class, medium effort | fast class, low effort |
| balanced (default) | frontier class, high effort | balanced class, medium effort |
| best | frontier class, max effort | frontier class, high effort |

A role may set a floor (`min_class`) and may require vision; the dial never goes below a role's floor. Advanced lets a single seat be overridden with a class or an exact model and an effort. Changing quality takes effect at each seat's next run.

- **LLM-4 Classes and lineups.** Each credential has a lineup mapping class (`frontier`, `balanced`, `fast`) to a model. Lineups are picked automatically from the models the credential can reach (newest model in each class) and refreshed daily. An admin may override them. When a class has no model on the paying credential, the seat runs on the nearest available class and the substitution is shown on the seat and in the chat header (P12). It is never hidden.
- **LLM-5 Effort.** One scale (low, medium, high, max), translated per model by the gateway. A model without effort control ignores it; an unsupported level rounds to the nearest supported one. Both are shown, never refused.
- **LLM-6 Seat check.** One shared function validates a seat at hire, edit, start and lease. It refuses only real blockers:
  - no credential on the project pays this provider;
  - the harness cannot authenticate with this credential kind;
  - the role needs the web and no search is available (INT-8);
  - the role needs vision and no vision model is available;
  - the CEO's harness cannot hold a chat.

  A seat refused at lease time fails before any sandbox starts and before any tokens are spent, and the reason is posted in the chat.
- **LLM-7 Who pays.** A project has one primary model credential and may add others for particular seats, plus an optional fallback. One resolver decides which credential pays a seat, and every lane uses it: work, chat and check. Chat and work runs never see different credentials.
- **LLM-8 Harness interface.** A harness drives the model inside the sandbox. It is transport only and never changes the rules. One interface covers:
  - start with a system prompt, a context pack, a tool set (the agent API as MCP tools, plus files, shell and web as the role grants), an effort level and limits;
  - stream progress;
  - honour cancellation;
  - state whether it can withhold each tool grant, hold a conversation, search, take images, and load skills natively (otherwise the agent API serves them, LIB-6).

  It reaches models only through the gateway with the run token. Ship at least one vendor-neutral loop that works with every provider and at least one vendor agent SDK pointed at the gateway. More harnesses are plug-ins. A scripted **mock** harness exists for tests and rehearsal. A harness that cannot use the gateway (some subscription-login CLIs) is allowed only with the weaker boundary stated in SECURITY.md (NFR-14).
- **LLM-9 Metering.** The gateway records every call's input, output, cache-write and cache-read tokens, attributed to run, seat, requirement and credential. It enforces the per-run cap (GOV-6) by refusing the next call past it. Harness-reported usage is only cross-checked.
- **LLM-10 Health.** "Smoke" makes one tiny real call. "Check" runs capability probes (follows exact instructions, tool arguments, uses tool results, parallel calls, effort, search, images) and five small tasks graded mechanically, never by another model. Token cost is shown first and metered. A daily upkeep job re-reads each credential's model list and flags seats on retired models before they fail.
- **LLM-11 Circuit breaker** per credential:
  - It opens after 3 consecutive transient failures. Cool-off starts at 5 minutes and doubles up to 1 hour, then a half-open probe.
  - While it is open, seats move to the fallback credential if one is set; otherwise they wait, and the chat header says so.
  - Authentication failures do not trip the breaker, but 3 consecutive ones pause the project (PRJ-2).
  - The chairman is told when a breaker opens and when it closes.
- **LLM-12 Provider ceilings.** An install-wide concurrency ceiling per provider keeps several projects sharing a key under its rate limits. Leasing looks past a saturated provider so one provider cannot block the others. An admin sets each ceiling; a provider with none is not limited, and there is no default.
- **LLM-13 Cost estimate (display only).** For API-key credentials the app MAY show an estimated money cost beside token figures, from a price catalog, labelled "estimate". Prices never gate hiring, never enforce anything and never appear as a budget.
- **LLM-15 Output standard in every call.** Every model call is told to answer in clear, plain English and to keep it short (P18).
  - **One copy.** The output standard is product content, kept once beside the Founder doctrine and published with the communication standard (MSG-12, LIB-6).
  - **Every call.** The platform places it in the system prompt of every model call it makes or prepares, whatever the harness:
    - agent work runs and chat runs;
    - the Founder;
    - the memory extractor;
    - image descriptions;
    - the lint rewrite (MSG-12);
    - goal grading, and capability checks with a graded answer.
  - **What it says:**
    - lead with the answer;
    - no preamble, no restating the question and no closing summary;
    - no filler, flattery or hedging;
    - plain words over jargon;
    - link instead of pasting.
  - **When the task asks for length.** The content the task asks for (a deliverable, code, a detailed report the chairman requested) follows the task, and the message around it stays short.
  - **Checked.** A test enumerates every path that builds a prompt, and fails if one omits the standard.
  - **Measured, not refused (P1).** Output tokens per message are shown per seat in the run health report, beside the lint results of MSG-12.
- **LLM-14 Platform models.** The Founder's drafting model and the memory extractor's model are platform settings and can use any provider. The memory layer's embedding model defaults to a bundled open-source model running locally, so it needs no key (MEM-2).
