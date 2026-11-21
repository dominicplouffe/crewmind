## 12. Lessons from v1: what the rebuild must design out

v1's ideas are mostly right; its structure is what failed. It grew to about 87,000 lines of Python, 40,000 of TypeScript, 68 tables, about 330 HTTP routes, 37 MCP tools, about 100 CLI commands and 73 schema migrations in about seven weeks. The table lists each structural failure, what it cost, and the rule that prevents it. User-facing failures are in section 1.5.

| v1 failure | What it cost | Rebuild rule |
| --- | --- | --- |
| A concept was wired into half the places it belongs, and nothing failed when one was missing | Screens went quietly stale; approvals never reached the desk | Concepts register once; surfaces are generated; a missing surface fails the conformance test (IF-1.3) |
| No service layer: rules lived in large HTTP handler files, and the MCP server called handlers directly; CLI and web client were hand-written a third and fourth time | Logic duplicated and drifted | Domain modules own their rules, commands, read models and jobs; every surface is a thin adapter (IF-1.1, IF-1.2) |
| Files organised by caller, not domain: a 7,300-line admin router, a 3,400-line policy file with about 270 refusal sites, a 3,200-line janitor | Changes were hard to place and review | One module per domain; no catch-all files |
| Too many overlapping "needs a human" objects | Every new kind re-wired everywhere | One decision-item type with registered kinds (HUM-1, HUM-2) |
| State held as strings: free-text statuses, 67 JSON columns, control flow matching refusal prose | Invalid states were representable; wording changes broke behaviour | Enumerated states with transitions declared once (section 7), typed events, no logic that depends on prose |
| Style rules enforced as refusals (word caps, sentence caps, report cadence) | Agents fought refusal loops | Style is measured and fed back (MSG-12); hard rules cover authority, budget, side effects, scope and verification (P1) |
| Run-count limits, inbox limits, a $2 per-run cap and a 30-minute timeout | 1,224 useful runs killed; the chairman raised inbox limits about 10 times; replies silently stopped | Token budget as the wall, a 3M-token per-run cap, a 90-minute timeout, runaway guards instead of run counts, and every hold visible (GOV-3, GOV-7, EXE-4) |
| Money and credentials changed about 13 times in 4 weeks, including a dollar/token conversion replaced within a week | Billing bugs; seats that could not run | One unit for the budget (tokens), one gateway that meters, one "who pays" resolver for every lane (LLM-7, LLM-9) |
| Model and effort chosen per role and seat | The chairman could not choose well; seats refused for unsupported effort | One quality dial; lineups automatic; substitutions shown, not refused (LLM-3 to LLM-5) |
| The chat lane and work lanes disagreed: stale credentials, duplicate answers, shared read marks stealing messages | The chairman saw contradictions | One conversation model and one credential resolver for every lane (MSG-13, LLM-7) |
| A session crash (exit 137) lost a plan, and nothing woke the CEO | Lost work and silence | Plans are stored state written as made; crashes retry with saved notes (MEM-7, EXE-8) |
| Scorecards frozen when written, then fixed by seven history-rewriting migrations | Data rewrites | Reports derived from the event log when read (NFR-10) |
| Two databases (SQLite and Postgres); SQLite could not exercise half the migrations | Green tests for a database nobody deployed | Both databases run the whole test suite and every migration in CI (NFR-8) |
| Six harnesses and a 2,800-line sandbox entry point; one interpreter difference killed every seat on one harness | Fragility | One harness interface, few harnesses, plug-ins for more (LLM-8) |
| About 2,700 slow HTTP tests, meta-tests policing source, golden evals freezing prompt wording | Slow CI; tests that encoded incidents | Fast domain tests, thin contract tests, attack tests, behaviour-level scenarios (NFR-19) |
| Metaphor identifiers and incident-narrating comments | Code hard to follow | Plain domain names (NFR-21) |

**What v1 got right and must be kept:**

- the server-enforced rule thesis (P1);
- per-run scoped tokens;
- metering of failed runs;
- zero-cost idle;
- platform-run verification;
- deny-by-default for silence and for write tools;
- two-phase MCP confirmation with machine attribution;
- the untrusted-content envelope;
- the Founder's goal grammar and doctrine;
- attack tests for every rule.

The role library, crews, examples, doctrine and goal grammar are imported as content.
