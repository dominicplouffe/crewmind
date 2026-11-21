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

Status: phase 3 (listening) is built on top of phase 2 (chat and execution). You can talk to a CEO agent in the web app or the terminal. What you say once sticks: standing orders, decisions and corrections reach every run word for word, and agents recall facts from earlier work. Tasks, verification and planning come in later phases. See [docs/PLAN.md](docs/PLAN.md) for the phases, [docs/phases/](docs/phases/) for what each phase did and did not finish, and [SECURITY.md](SECURITY.md) for what is and is not protected.

## Try it

Build the web app once (needs Node 22):

```bash
cd web && npm ci && npm run build && cd ..
```

Fetch the local embedding model once (about 70 MB; memory works offline after that):

```bash
uv sync
```

```bash
uv run python -m crewmind.domain.memory.fetch_model
```

Set up a slim install (one process, SQLite) and start it. `unisolated` runs agents as plain processes, which is fine for a first look on your own machine; the default, `container`, needs Docker.

```bash
uv sync
```

```bash
uv run crewmind setup --slim --admin-email you@example.com
```

```bash
CREWMIND_SANDBOX_MODE=unisolated uv run crewmind up --slim
```

Open the setup link that `setup` printed, set a password, sign in at `http://127.0.0.1:8420`, and create a project.

To get real answers, add a model credential in another terminal. The key is read from a file or standard input, never from the command line:

```bash
uv run crewmind login --email you@example.com
```

```bash
uv run crewmind credentials add --name main --provider anthropic --key-file ~/anthropic.key
```

```bash
uv run crewmind models set-payer --project-id <id> --credential main
```

Start the project and say hello, in the browser or in the terminal:

```bash
uv run crewmind chat --project Atlas
```

Without a credential, a project runs on the mock provider, which answers from scripts in `CREWMIND_MOCK_SCRIPT_DIR` and costs nothing.

## Develop

```bash
uv sync
uv run pytest                 # SQLite
uv run pytest --db=postgres   # reads CREWMIND_TEST_POSTGRES_URL
uv run ruff check && uv run ruff format --check && uv run pyright
```

The web app has its own checks; see [web/README.md](web/README.md).
