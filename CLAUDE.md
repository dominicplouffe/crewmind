# nightsquad: instructions for Claude Code

nightsquad runs a team of AI agents like a company (chairman, CEO, teams) under rules the agents cannot talk their way out of. This repository is a rebuild from an empty start. The specification in `docs/spec/` is the source of truth.

## Before any work

1. Read `docs/spec/00-how-to-use.md`, `docs/spec/02-principles.md` and `docs/spec/08-invariants-INV.md`. They override everything else.
2. Read `docs/PLAN.md` and work only on the current phase. Do not build ahead.
3. Read the spec files the current phase lists. Do not load the whole spec at once unless asked.

## Rules that are never broken

- **Principles (P1–P18) and invariants (INV-1 to INV-26) are not negotiable.** If a task would break one, stop and say so.
- **The spec is changed only by editing `docs/spec/`,** in the same change as the code, with a line in `docs/spec/CHANGELOG.md`. Never let code silently disagree with the spec.
- **When the spec is unclear, contradictory or untestable, do not guess.** Add an entry to `docs/spec-questions.md` (id, quote, the question, your recommendation) and ask the owner. Continue with other work meanwhile.
- **One operation, one implementation (P11, IF-1.1 to IF-1.4).** Every domain action is defined once in the operation catalog. HTTP routes, CLI commands, MCP tools, slash commands, Slack actions and agent API tools are thin adapters with no business rules. The conformance test (IF-1.3) must pass on every commit.
- **No magic numbers.** Every tunable number is a setting in the registry (`docs/spec/appendix-a-settings.md`), read through the settings service. A number in code without a setting name must be a fixed rule the spec states.
- **States are declared once.** Lifecycles come from the tables in `docs/spec/07-state-machines.md`. A transition not in the table is refused.
- **Secrets never reach a sandbox, a log, a trace, an export or an agent-facing response (INV-6).** Model calls go through the model gateway only (P3).
- **Plain domain names in code (section 4, NFR-21).** No metaphors, and no comments that narrate incidents.

## Stack (NFR-24)

- Python 3.12+, managed with `uv`. FastAPI + Pydantic v2, SQLAlchemy 2 + Alembic, Typer (CLI), Textual (`squad chat`), the official MCP Python SDK, LiteLLM (inside the model gateway), Mem0 (recall memory), Docker SDK, Playwright, OpenTelemetry SDK.
- Background work: asyncio workers that lease from the database. No Redis and no broker.
- Databases: Postgres (with pgvector) and SQLite. **Both from the first commit.** Domain logic never depends on one database's features except behind the storage adapter.
- Web app: TypeScript + React in `web/`, with its API client generated from the OpenAPI schema. The only other non-Python code is the bash scripts in `deploy/` that run the Docker install (ADR-0009). They hold no product rules: they call the server's own operations.
- Recording a deviation from a SHOULD library: add a decision record in `docs/decisions/`.

## Layout

```
src/nightsquad/
  catalog/            operation registry, schemas, authority, reversibility, the one call path
  domain/<module>/    one module per domain: rules, state machines, commands, read models
                      (projects, settings, budget, planning, work, artifacts, conversation,
                       decisions, execution, models = credentials and lineups, memory, founder,
                       library, integrations, accounts, record = the event log, secrets,
                       install = host-local commands)
  jobs/               the scheduler and its periodic jobs
  surfaces/           api/, cli/, mcp/, slash/, agent_api/, slack/: adapters only
  gateway/            model gateway (LiteLLM), metering, per-run caps
  runner/             leasing, sandboxes, harnesses (mock first)
  storage/            SQLAlchemy models, Alembic migrations, the storage adapter
  content/            packaged copies of content the server reads at run time
  live.py             the in-process hub that feeds the live event stream
web/                  TypeScript/React app
deploy/               Dockerfiles, Compose file and shell scripts for a full server
tests/
  unit/  contract/  attack/  chaos/  scenarios/  acceptance/
content/              imported v1 roles, squads, doctrine, goal grammar
acceptance/           reference specs used by the acceptance suite
```

Keep files small and focused. A file growing past about 600 lines is a sign it holds more than one concept.

## Tests

- `uv run pytest`: default suite. It never calls a paid model or the network; use the mock harness.
- Tests that use the real memory engine need the embedding model on disk: `uv run python -m nightsquad.domain.memory.fetch_model` once. Without it they skip and say so. Every other test uses the in-process memory engine.
- `uv run pytest --db=sqlite` and `uv run pytest --db=postgres`: both must pass. CI runs both.
- **Every enforced rule gets an attack test** in `tests/attack/` that tries to break it through the public API the way an agent would (P10).
- **State machines get table-driven tests plus Hypothesis property tests.**
- **Name tests after the requirement they prove** (for example `test_GOV_3_wall_pauses_project`), and list requirement ids in the docstring.
- Golden scenarios assert behaviour, never prompt wording.
- **Tests must stay fast as they multiply.** The suite runs in parallel (`-n auto` is the default), so:
  - Every test is independent: its own database (the `runtime` and `app` fixtures copy a migrated template; never migrate per test), its own temporary directory, no shared files, no fixed ports, no reliance on test order.
  - No real waiting. Move the `FakeClock` instead of sleeping; drive jobs with `tick()` instead of waiting for them.
  - Test a rule at the lowest layer that proves it. Start a real server process only in `tests/acceptance/`, and keep those few.
  - One test longer than 10 seconds fails the suite unless it is in `tests/acceptance/` (marked `slow`). `uv run pytest -m "not slow"` is the quick loop while developing.
  - Prefer one parametrized or table-driven test over many near-copies.
- `uv run ruff check`, `uv run ruff format --check` and `uv run pyright` must be clean.

## Definition of done for a change

1. The requirement ids it implements are cited in the code docstrings, the tests and the commit message.
2. Tests pass on both databases, including attack tests for any rule touched.
3. The conformance test passes.
4. `docs/traceability.csv` is updated: status, and the tests that cover each id.
5. Any spec change is in `docs/spec/` with a CHANGELOG line.

## Commits

Format: `<area>: <what changed> [GOV-3, INV-9]`. One concern per commit.
