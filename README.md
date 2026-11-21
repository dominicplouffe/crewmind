# crewmind

crewmind runs a team of AI agents like a company, unattended, for hours to weeks, under rules the agents cannot talk their way out of. You state a goal in a chat, and the platform staffs a CEO agent and specialist teams and gives them a token budget. They work fast while you stay in charge as chairman.

This repository is the rebuild (v2). It starts from the specification, with no v1 code.

| Where | What |
| --- | --- |
| [docs/spec/](docs/spec/README.md) | The specification: the source of truth |
| [docs/PLAN.md](docs/PLAN.md) | Build plan: phases, the v2.0 cut line, exit criteria |
| [docs/decisions/](docs/decisions/) | Decision records for choices already made |
| [docs/traceability.csv](docs/traceability.csv) | Every requirement id, its phase, status and tests |
| [docs/spec-questions.md](docs/spec-questions.md) | Open questions raised while building |
| [CLAUDE.md](CLAUDE.md) | Rules for coding agents |
| [acceptance/](acceptance/README.md) | Reference specs the acceptance suite runs |
| [content/](content/README.md) | v1 content to import (roles, crews, doctrine) |

Status: phase 0 (bootstrap) is built. See [docs/PLAN.md](docs/PLAN.md) for the phases.

## Develop

```bash
uv sync
uv run pytest                 # SQLite
uv run pytest --db=postgres   # reads CREWMIND_TEST_POSTGRES_URL
uv run ruff check && uv run ruff format --check && uv run pyright
```
