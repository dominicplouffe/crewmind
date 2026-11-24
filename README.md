# Nightsquad

Nightsquad runs a team of AI agents like a company, unattended, for hours to weeks, under rules the agents cannot talk their way out of. You state a goal in a chat, and the platform staffs a CEO agent and specialist teams and gives them a token budget. They work fast while you stay in charge as chairman.

This repository is the rebuild (v2). It starts from the specification, with no v1 code.

| Where | What |
| --- | --- |
| [docs/spec/](docs/spec/README.md) | The specification: the source of truth |
| [docs/PLAN.md](docs/PLAN.md) | Build plan: phases, the v2.0 cut line, exit criteria |
| [docs/decisions/](docs/decisions/) | Decision records for choices already made |
| [docs/traceability.csv](docs/traceability.csv) | Every requirement id, its phase, status and tests |
| [docs/spec-questions.md](docs/spec-questions.md) | Open questions raised while building |
| [HANDOVER.md](HANDOVER.md) | Where the build stands and how to carry it on |
| [CLAUDE.md](CLAUDE.md) | Rules for coding agents |
| [acceptance/](acceptance/README.md) | Reference specs the acceptance suite runs |
| [content/](content/README.md) | The role and squad library, example specs, the Founder's doctrine and the goal grammar |

Status: phases 2 to 7 are built: chat and execution, listening, verification, planning, the chairman loop, and the Founder with rehearsal. This is the v2.0 release candidate. You can draft a project by talking to the Founder, and rehearse it at no cost before it starts. You can talk to a CEO agent in the web app or the terminal. What you say once sticks; agents recall earlier work; tasks are done only when the platform or another agent has checked them; every task serves scope you can see; and everything that waits on you is one kind of item, with a deadline and a stated outcome if you do nothing. The desk lists what waits on you, the daily brief and the agenda are built from the record at no cost, and an AI client of your own can steer a project over MCP within the scopes you grant. The Founder and integrations (Slack, mail, data sources) come in later phases. See [docs/PLAN.md](docs/PLAN.md) for the phases, [docs/phases/](docs/phases/) for what each phase did and did not finish, and [SECURITY.md](SECURITY.md) for what is and is not protected.

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
uv run python -m nightsquad.domain.memory.fetch_model
```

Set up a slim install (one process, SQLite) and start it. `unisolated` runs agents as plain processes with no isolation, which is fine for a first look on a machine you can lose. For agents in containers, use the server install below.

```bash
export NIGHTSQUAD_SANDBOX_MODE=unisolated
```

```bash
uv run squad setup --slim --admin-email you@example.com
```

```bash
uv run squad up --slim
```

Open the setup link that `setup` printed, set a password, sign in at `http://127.0.0.1:8420`, and create a project. Use that exact address: the server refuses a browser session from any other, `http://localhost:8420` included.

To get real answers, add a model credential in another terminal. The key is read from a file or standard input, never from the command line:

```bash
uv run squad login --email you@example.com
```

```bash
uv run squad credentials add --name main --provider anthropic --key-file ~/anthropic.key
```

```bash
uv run squad models set-payer --project-id <id> --credential main
```

Start the project and say hello, in the browser or in the terminal:

```bash
uv run squad chat --project Atlas
```

To let an AI client of your own work with your projects, mint it a token with the scopes you choose (`read`, `steer`, `create`, `configure`) and point the client at `http://127.0.0.1:8420/mcp`:

```bash
uv run squad mcp-clients mint --client-name "Desk assistant" --scopes steer
```

A client that speaks OAuth can register itself and ask you to approve it instead. Either way, a write that cannot be undone takes two calls, and a few things stay yours alone: membership, credentials and deleting a project.

Without a credential, a project runs on the mock provider, which answers from scripts in `NIGHTSQUAD_MOCK_SCRIPT_DIR` and costs nothing.

Starting a project wakes its CEO at once to plan. Type `/plan` in the chat, open the Plan panel, or run:

```bash
uv run squad plan show --project-id <id>
```

The plan lists the requirements (or bets), what is ready for work, the projection, the commitment, the CEO reserve and where the time went. `squad desk show` lists everything that waits on you across projects, `squad items decide` answers one, `squad brief show` gives the last day, and `squad agenda show` says what happens next. Add scope yourself with `squad requirements add`, and finish a ready Deliver project with `squad projects sign-off`.

To draft a project by talking, an admin first names the credential the Founder itself runs on. Then start a conversation in the web app ("Start a project") or in the terminal:

```bash
uv run squad settings change-install --changes founder.credential=main --reason "The Founder's model."
```

```bash
uv run squad draft
```

The Founder drafts first and then asks one decision at a time, each with its recommended answer: Enter accepts it. A pasted or attached brief is grilled before anything is drafted from it. `squad draft --quick` lets the Founder decide everything and start the project. To check how well your model grades goals against the hand-graded references:

```bash
uv run squad founder eval --goal acceptance/reference-goal.md --grades acceptance/reference-goal.grades.json --goal acceptance/raw-brief.md --grades acceptance/raw-brief.grades.json
```

A project is one portable file, a spec. `squad projects export` writes it, `projects import-spec` and `projects clone` create from it, and a rehearsal runs it through the real rules with a squad in code, spending nothing:

```bash
uv run squad projects rehearse --project-id <id>
```

## Install on a server

The full server runs in Docker: Postgres, the server, a TLS front, and each agent run in a container of its own. It needs Docker with the Compose plugin, `openssl` and `curl`.

```bash
deploy/deploy_single_server.sh --admin-email you@example.com
```

That builds two images (several minutes the first time), starts everything, and prints a link where you set your password. By default it listens on this machine only, at `https://localhost`. To reach it from another machine, name the address to listen on:

```bash
deploy/deploy_single_server.sh --bind 192.168.1.50
```

People then sign in at `https://192.168.1.50`. Running the script again is safe: it keeps the address and never replaces a secret.

| Script | What it does |
| --- | --- |
| `deploy/deploy_single_server.sh` | Install, or start again on the code that is checked out |
| `deploy/update_single_server.sh` | Pull, back up, rebuild, restart. Refuses a checkout with local edits; `--dry-run` changes nothing |
| `deploy/backup_single_server.sh` | One file with the database, the master key and the artifacts |
| `deploy/restore_single_server.sh <file>` | Put a backup back. Saves what is there first, and asks you to type `restore` |
| `deploy/kill_single_server.sh` | Stop and keep the data. `--wipe` also destroys the database, after you type `DESTROY` |

Each takes `--help`.

- **The address must match.** Sign in only at the address the script prints. The server refuses a browser session from any other.
- **The certificate.** The TLS front signs its own certificate, so a browser asks you to accept it once. Until the certificate is trusted, push alerts and the installable app do not work. For a public host name, use `--bind 0.0.0.0 --public-url https://squad.example.com --tls you@example.com` and it gets a certificate from Let's Encrypt.
- **Docker ignores `ufw`.** A port Docker publishes is open whatever the firewall says. The listen address is what keeps it private.
- **Back up the master key.** It is `master.key` in the state directory (`/var/lib/nightsquad` unless you pass `--state-root`). Without it no stored model key can be read. The backup script includes it.
- **The `squad` command** runs inside the server:

```bash
docker compose -f deploy/compose.yaml exec server squad doctor
```

Model keys are read from a file or from standard input, so pipe one in:

```bash
docker compose -f deploy/compose.yaml exec -T server squad credentials add --name main --provider anthropic --key-stdin < ~/anthropic.key
```

[SECURITY.md](SECURITY.md) says what a container does and does not contain.

## Develop

```bash
uv sync
uv run pytest                 # SQLite
uv run pytest --db=postgres   # reads NIGHTSQUAD_TEST_POSTGRES_URL
uv run ruff check && uv run ruff format --check && uv run pyright
```

The web app has its own checks; see [web/README.md](web/README.md).

`uv run pytest -m slow` runs the few tests that start a real server, among them the speed criterion: a scripted squad in `acceptance/scripts/deliver-reference.json` must take a four-page project from start to ready in no more than 1.3 times its longest chain of runs. A mock script file is a list of turns replayed in every run, or `{"runs": [[...], [...]], "then": [...]}` to give each run of a seat its own turns; a turn may set `delay_ms` to take time.
