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

Status: phases 2 to 6 are built: chat and execution, listening, verification, planning, and the chairman loop. You can talk to a CEO agent in the web app or the terminal. What you say once sticks; agents recall earlier work; tasks are done only when the platform or another agent has checked them; every task serves scope you can see; and everything that waits on you is one kind of item, with a deadline and a stated outcome if you do nothing. The desk lists what waits on you, the daily brief and the agenda are built from the record at no cost, and an AI client of your own can steer a project over MCP within the scopes you grant. The Founder and integrations (Slack, mail, data sources) come in later phases. See [docs/PLAN.md](docs/PLAN.md) for the phases, [docs/phases/](docs/phases/) for what each phase did and did not finish, and [SECURITY.md](SECURITY.md) for what is and is not protected.

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

To let an AI client of your own work with your projects, mint it a token with the scopes you choose (`read`, `steer`, `create`, `configure`) and point the client at `http://127.0.0.1:8420/mcp`:

```bash
uv run crewmind mcp-clients mint --client-name "Desk assistant" --scopes steer
```

A client that speaks OAuth can register itself and ask you to approve it instead. Either way, a write that cannot be undone takes two calls, and a few things stay yours alone: membership, credentials and deleting a project.

Without a credential, a project runs on the mock provider, which answers from scripts in `CREWMIND_MOCK_SCRIPT_DIR` and costs nothing.

Starting a project wakes its CEO at once to plan. Type `/plan` in the chat, open the Plan panel, or run:

```bash
uv run crewmind plan show --project-id <id>
```

The plan lists the requirements (or bets), what is ready for work, the projection, the commitment, the CEO reserve and where the time went. `crewmind desk show` lists everything that waits on you across projects, `crewmind items decide` answers one, `crewmind brief show` gives the last day, and `crewmind agenda show` says what happens next. Add scope yourself with `crewmind requirements add`, and finish a ready Deliver project with `crewmind projects sign-off`.

## Develop

```bash
uv sync
uv run pytest                 # SQLite
uv run pytest --db=postgres   # reads CREWMIND_TEST_POSTGRES_URL
uv run ruff check && uv run ruff format --check && uv run pyright
```

The web app has its own checks; see [web/README.md](web/README.md).

`uv run pytest -m slow` runs the few tests that start a real server, among them the speed criterion: a scripted crew in `acceptance/scripts/deliver-reference.json` must take a four-page project from start to ready in no more than 1.3 times its longest chain of runs. A mock script file is a list of turns replayed in every run, or `{"runs": [[...], [...]], "then": [...]}` to give each run of a seat its own turns; a turn may set `delay_ms` to take time.
