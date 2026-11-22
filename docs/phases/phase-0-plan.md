# Phase 0 plan: bootstrap

Goal (PLAN.md): stand up the guardrails before any feature. No domain features are built here.

## Exit criteria

1. CI is green on SQLite and on Postgres with the skeleton.
2. The conformance test fails when an operation is registered without an adapter.
3. `crewmind --help` runs.
4. The spec review is answered (done: spec revision 2.1).

## Decisions this plan makes

| Decision | Choice | Why |
| --- | --- | --- |
| Python | 3.12 or later; developed on 3.13 | NFR-24 |
| Build | `uv`, `hatchling`, source in `src/crewmind` | CLAUDE.md layout |
| Database access | SQLAlchemy 2 async: `aiosqlite` for SQLite, `psycopg` 3 for Postgres. Alembic runs the same URLs synchronously | FastAPI and the asyncio workers are async (NFR-24); one Postgres driver serves both modes |
| HTTP route shape | One route per operation, derived from its name: `projects.hold` becomes `POST /v1/projects/hold`. Operations of class `read` use `GET` with query parameters | IF-3.1; routes are generated, so the shape is a single rule |
| CLI command shape | `crewmind <group> <verb>`, generated from the same name. Scalar inputs become options; anything else goes through `--input` as JSON. Every command has `--json` (IF-4.3) | IF-1.2 |
| MCP tool shape | One tool per operation, named with underscores (`projects_hold`), input schema from the Pydantic model | IF-1.2 |
| Settings data | A TOML file in the package, transcribed from Appendix A. A test parses the Appendix A tables and fails on any difference in names, scopes, defaults, ranges or "Used by" | "Loaded from Appendix A as data" without shipping the docs in the wheel; drift cannot pass CI |

## Modules

```
src/crewmind/
  catalog/
    operation.py     Operation: name, input and output models, authority, reversibility,
                     audit actor, slash command, principals, host-local flag, exemptions (IF-1.1)
    registry.py      Catalog: register, look up, enumerate; the one process-wide catalog (empty)
    surfaces.py      The six surfaces, which principals reach which, surfaces not yet built (IF-1.2)
    conformance.py   check_conformance(catalog, built surfaces) -> violations (IF-1.3)
    refusal.py       Refusal: code, rule, message, hint; the shared error envelope (IF-1.4, IF-3.4)
    rules.py         Rule registry: id, sentence, mode enforce or warn (NFR-20)
  domain/settings/
    registry.toml    Every setting, constraint and operational variable in Appendix A
    registry.py      Typed loader, lookup, value validation against type and range
  surfaces/
    api/app.py       FastAPI app generated from the catalog; maps Refusal to the envelope
    cli/main.py      Typer app generated from the catalog; `crewmind` entry point
    mcp/server.py    MCP server (official SDK) with tools generated from the catalog
  runner/harness/
    base.py          Harness interface (LLM-8): start, stream progress, cancel, capabilities
    mock.py          Scripted mock harness: replays a script, no network, no tokens
  storage/
    engine.py        Engine factory for both databases; URL handling
    migrations/      Alembic environment and an empty baseline migration
```

No operation is registered in phase 0. Adapters are exercised with sample operations defined in the tests.

## Tests, written first

| Test | Proves |
| --- | --- |
| `tests/contract/test_IF_1_3_conformance.py` | The real catalog conforms on `api`, `cli` and `mcp`. With a sample operation left off one surface, the check reports it. A written exemption silences exactly that operation and surface. An unbuilt surface is exempt as a whole. A host-local operation is not expected on `api` or `mcp` (IF-4.2) |
| `tests/contract/test_IF_1_2_adapters.py` | A sample operation is callable through the API route, the CLI command and the MCP tool, and all three reach the one handler |
| `tests/contract/test_IF_1_4_refusals.py` | A refusal raised by a handler has the same code, rule, message and hint on API, CLI and MCP |
| `tests/unit/test_catalog.py` | Duplicate names, bad names and missing fields are refused at registration |
| `tests/unit/test_settings_registry.py` | The TOML matches Appendix A exactly. Every default passes its own validation. Hypothesis: any in-range value passes and any out-of-range value is refused |
| `tests/unit/test_mock_harness.py` | The mock harness replays a script in order, reports its capabilities and stops on cancel |
| `tests/unit/test_storage.py` | The baseline migration applies on the selected database and the engine answers a query. Runs under `--db=sqlite` and `--db=postgres` |
| `tests/attack/test_P10_attack_coverage.py` | Every rule in the rule registry has at least one attack test marked with its id. A rule without one fails the check |
| `tests/attack/harness.py` | Helpers for later phases: call the API as a foreign, forged or missing principal, and assert a refusal by code and rule |
| `tests/unit/test_cli.py` | `crewmind --help` exits 0 |

## Tooling

- `ruff check`, `ruff format --check`, `pyright` in strict mode: all clean.
- `uv run pytest` defaults to SQLite. `--db=postgres` reads `CREWMIND_TEST_POSTGRES_URL`.
- CI (GitHub Actions): one lint job; one test job per database, with a `pgvector/pgvector:pg16` service for Postgres. The workflow is in `ci/github-actions.yml` and runs once the owner copies it to `.github/workflows/ci.yml`.

## Not in phase 0

Accounts, projects, the event log, the settings service (changing settings, GOV-1), authentication on any surface, MCP transport and tokens, the web app, and real sandboxes. These are phase 1 and 2.

## Open questions

None blocking. Two choices above are easy to change now and costly later: the route shape and async database access.
