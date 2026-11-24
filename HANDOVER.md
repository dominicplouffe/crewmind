# Handover

For whoever continues this build, person or coding agent. Everything needed is in this repository; nothing lives only in a chat.

## Where things stand (22 Nov 2026)

- Phases 0 to 7 are built on the branch `claude/sharp-franklin-td8qhd`. There is no pull request and nothing is merged to the default branch.
- Phase 7 is the v2.0 release candidate, with one condition: the Founder has only ever been driven by a scripted model. See "Before anything else".
- Docker support was finished after phase 7 (22 Nov 2026): the agent image, container sandboxes and checks proven on a real daemon, and a Compose install with a TLS front, driven by shell scripts in `deploy/` (deploy, update, backup, restore, kill).
- Next is phase 8 (`docs/PLAN.md`). No phase 8 plan is written.
- The product was renamed nightsquad on 24 Nov 2026 (ADR-0011), on branch `claude/lucid-franklin-gwvmmu`. The CLI command is `squad`, also installed as `nightsquad`, and the library's ready-made job is a squad. Migrations 0017 and 0018 carry existing data, and `squad doctor` names old variables and folders. Still the owner's to do: rename the GitHub repository, register the domains, reserve `nightsquad` on PyPI and npm, and confirm trademark clearance.

## Read in this order

1. `CLAUDE.md`: the rules. They are not negotiable.
2. `docs/spec/00-how-to-use.md`, `02-principles.md`, `08-invariants-INV.md`.
3. `docs/PLAN.md`, then the newest file in `docs/phases/`. Each phase file ends with an "Outcome" section that says, honestly, what passed, what is partial and what was found and not fixed. `docs/phases/phase-7-plan.md` is the current state of the product.
4. `docs/spec-questions.md`: questions waiting for the owner.
5. `docs/traceability.csv`: every requirement id, its status, its tests and a note.

## Before anything else

1. **Run the Founder against a real model.** Set `founder.credential`, draft one real project, and run `squad founder eval` (the README has the commands). Record what you find in `docs/phases/phase-7-plan.md`.
2. **The owner answers Q-012 to Q-018** in `docs/spec-questions.md` (v1 effort levels, squad estimates, dropped v1 settings, the reworded charters and doctrine, the new settings).
3. **Copy `ci/github-actions.yml` to `.github/workflows/`** so both databases run on every push. CI has never run. It now builds the agent image first, so the container tests run there.
4. **The owner answers Q-019:** how a slim install on Linux reaches its sandboxes.

## How each phase is done

1. Write `docs/phases/phase-N-plan.md`: what it covers, its parts, what stands in for later phases, tests to write first, review items from `docs/spec-review.md` marked for that phase, risks, and questions.
2. Ask the owner the questions. Record the answers in the plan and apply accepted review items to `docs/spec/` with a `CHANGELOG.md` section.
3. Build part by part. After each part: both databases green, one concern per commit, push.
4. One review stop at the end: write the Outcome section and report to the owner, leading with what is not proven.

## Owner decisions that stand

- One review stop per phase, at the end. Reports are plain, short and honest: lead with the outcome, list every partial.
- No test calls a real model provider (Q-006). The mock provider and scripts stand in.
- Every model-facing text must produce clear, concise, plain English.
- Solo projects (one agent) must work.
- Outbound mail is phase 8. Until then alerts and briefs go by browser push and in the app.
- The v1 content came from `dominicplouffe/yaaf` (public, Apache-2.0), commit `b43bb78`. The unconverted originals are in git history at commit `d5bb608`.

## Working notes that are easy to miss

- **Commands.** `uv run pytest -m "not slow" --db=sqlite` and `--db=postgres`; `uv run pytest -m slow --db=postgres` for the real-server tests (run them on Postgres: one test only runs there); `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`. In `web/`: `npm run gen:api`, `npm run lint`, `npm run build`, `npm test`, `npm run e2e -- --trace off`.
- **Check the last line of a test run, not the exit of a pipe.** A command chained after `tail` commits even when tests failed. Postgres also stops between sessions in a cloud container (`pg_ctlcluster 16 main start`); a stopped Postgres shows as hundreds of setup errors, not as a failure of your change.
- **One migration per phase,** regenerated from the models while the phase is open: `uv run python scripts/dev/write_migration.py 0015 "phase 8 ..."`, then set `HEAD` in `tests/unit/test_storage.py`. The generator cannot order "add a column, fill it, then constrain it": phase 7's migration (`0014`) was patched by hand for that, so do not regenerate `0014`.
- **`scripts/dev/` holds rough working scripts** and is left out of the lint checks.
- **Traceability.** `python3 scripts/dev/apply_trace.py "ID" "ID=partial:note"` sets the status and finds the tests that name the id. The file has CRLF line endings; keep them.
- **After adding or changing an operation:** regenerate `web/openapi.json` (`uv run python -m nightsquad.surfaces.api.schema > web/openapi.json`) and `npm run gen:api`. Several catalog-walking tests then tell you what else to do: `test_INV_21_every_write_operation_records_an_event` (record an event, or list the operation in `NO_EVENT` with the test that asserts it), `test_INV_6_no_operation_output_carries_a_secret...`, `test_IF_5_2_every_person_operation_has_a_scope_or_a_stated_reason` (`src/nightsquad/catalog/mcp_scopes.py`), and `test_P10_every_registered_rule_has_an_attack_test`.
- **Never call a model with a database transaction open.** SQLite takes its write lock at the start of every transaction, so a model call that writes its ledger line from another session deadlocks. Use an operation's `prepare` step, or do the call between transactions.
- **Library content has two copies:** edit `content/`, then run `uv run python scripts/sync_content.py`. A test fails if they differ.
- **Container tests need Docker and the agent image:** `docker build -f deploy/agent.Dockerfile -t nightsquad-agent .`, then `uv run pytest tests/acceptance/test_containers.py`. Without either they skip. Rebuild the image when `src/nightsquad/runner/agent.py` changes: the image holds its own copy. The rest of the suite gives the same answers with or without Docker on the machine: a fixture hides the host's container socket, and acceptance installs name their sandbox mode.
- **The Compose database must match the server image's Postgres client tools** (both 17 now): backup and restore use `pg_dump` and `pg_restore` from the server image, and a newer client cannot restore into an older server. The test suite still runs on Postgres 16.
- **Tests must stay under 10 seconds each.** Start a real process only in `tests/acceptance/`. The rehearsal tests are the closest to the limit.
- **The settings registry and Appendix A must match,** in the same order; a test compares them. Bump the registry's `version` when you add a setting.
- **Web work was delegated to a sub-agent with a written brief** each phase, then checked by running lint, build, unit and browser tests. Nobody has looked at the pages by eye since phase 5.

## Known weak spots, in one place

- The Founder, the grader and every agent charter are unproven against a real model.
- Multi-provider and the section 1.3 timing targets were never measured.
- No single test does create, steer, inspect and configure through one surface alone.
- The phase 4 and 5 guards are mirrored as flags, not folded into them.
- Three tests failed once in phase 6 and passed on rerun, unexplained.
- An answer of a single letter to a Founder question is always read as an option.
- Refusal hints name CLI commands, and the web shows them as written.
- The Compose install and its five scripts were each run by hand on Docker 29. No automated test starts them. The update script was run with `--no-pull` and with the image build replaced by a no-op, because the build session could not build without a proxy; a real pull and rebuild is untried.
- A slim install on a Linux host cannot run agents in containers (Q-019).
- With the Compose install's own certificate, a browser does not register the service worker until the certificate is trusted, so push alerts and the installable app need a real certificate or a trusted one.
- The agent image is one fixed set of tools (Python, Node, git). A project cannot add to it.
