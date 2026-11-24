# Plan: rename crewmind to Nightsquad, and "crew" to "squad"

Status: draft for the owner's approval. Nothing in this plan has been done yet.

## Scope, measured on the current tree

| What | Count |
| --- | --- |
| Tracked files | 1,020 |
| Files containing `crewmind` (any case) | 561 (3,269 occurrences) |
| Whole-word `crew` / `crews` / `Crew` | about 2,150 occurrences, mostly in tests and `web/src/crew` |
| Spec lines that use "crew" | 15, across 12 spec files |

There are no substring traps: no word in the repository contains "crew" except the names being renamed (`useCrew`, `DrillCrew`, `openCrew` are renamed too).

## Names after the rename

| Thing | Before | After |
| --- | --- | --- |
| Product name in prose | crewmind | Nightsquad |
| Python package and import root | `crewmind` (`src/crewmind`) | `nightsquad` (`src/nightsquad`) |
| PyPI / npm name | `crewmind` | `nightsquad` (both free on 24 Nov 2026) |
| CLI command | `crewmind` | `squad`, with `nightsquad` as a second name for the same entry point (see decision 1) |
| Environment variables | `CREWMIND_*` (about 30) | `NIGHTSQUAD_*` |
| Session cookie | `crewmind_session` | `nightsquad_session` |
| Token prefixes | `cm_ses_`, `cm_pat_`, `cm_mcp_`, `cm_lnk_`, `cm_run_`, `cm_refresh_`, `cm_code_` | `ns_ses_`, `ns_pat_`, ... (the leak scan patterns follow) |
| Default state root | `/var/lib/crewmind` | `/var/lib/nightsquad` |
| Docker images | `crewmind-server`, `crewmind-agent` | `nightsquad-server`, `nightsquad-agent` |
| Compose database name and user | `crewmind` | `nightsquad` |
| Slack channel prefix | `#crewmind-<project>` | `#nightsquad-<project>` |
| Install-alias mailbox | `crewmind+<project>@domain` | `nightsquad+<project>@domain` |
| Library concept (LIB-2) | Crew | Squad |
| Library operations | `crews.list`, `crews.show`, `crews.save` | `squads.list`, `squads.show`, `squads.save` |
| Event type | `crew.saved` | `squad.saved` |
| Table | `crews` | `squads` |
| File-format markers | `crewmind_role`, `crewmind_crew`, `crewmind_spec` | `nightsquad_role`, `nightsquad_squad`, `nightsquad_spec` |
| Content folders | `content/crews`, `src/crewmind/content/library/crews` | `content/squads`, `src/nightsquad/content/library/squads` |
| Web folder and components | `web/src/crew`, `CrewView`, `CrewStrip`, `CrewAssembled`, `CrewMember`, `strings.crew.ts` | `web/src/squad`, `SquadView`, `SquadStrip`, `SquadAssembled`, `SquadMember`, `strings.squad.ts` |
| Test harness | `Crew.start(app)`, `DrillCrew` | `Squad.start(app)`, `DrillSquad` |

Text that stays as it is: the history in `docs/spec/CHANGELOG.md`, ADR-0008 (marked superseded) and the phase reports in `docs/phases/`, which record what happened under the old name.

## Steps (one concern per commit, on branch `claude/lucid-franklin-gwvmmu`)

1. **Decision and spec** `[docs]`
   - Add ADR-0011 "The project is named Nightsquad", superseding ADR-0008, with the reasons (CrewAI, Paperclip, YokeBot) and the CLI choice.
   - Edit `docs/spec/`: crewmind becomes Nightsquad, crew becomes squad (LIB-2 "Squad", SPD-9 "No idle squad", FND-2/FND-9 "roles and squads", RHS-1, IF tables, the README index, the title of 06-14).
   - Add one line to the spec CHANGELOG. Requirement ids do not change.
2. **Package move** `[all]`
   - `git mv src/crewmind src/nightsquad`, then rewrite every import.
   - Update `pyproject.toml`: the project name, scripts `squad` and `nightsquad`, the ruff and pyright paths, and the hatch artifact paths.
   - Regenerate `uv.lock`, and update the Alembic `env.py` and migration imports.
   - This commit changes names only, so tests must pass unchanged in meaning.
3. **Operational names** `[IF-4.1, INV-6]`
   - Environment variables in `domain/settings/registry.toml` and everywhere they are read.
   - Cookie name, token prefixes, leak-scan patterns, state root, Docker images, Compose and `deploy/*.sh`, the Slack prefix and the mailbox alias.
   - Attack tests that hold token strings or prefixes are updated with them.
4. **Squad concept** `[LIB-2, IF-1.3]`
   - Model `Crew` becomes `Squad`.
   - Migration `0017_rename_crews_to_squads`: rename the table and its indexes and constraints, and convert stored `crew.saved` event types (see decision 2).
   - Operations `squads.*`, the event type, API routes and MCP tools, and the CLI subcommand.
   - File-format markers, with import accepting the old marker (see decision 2).
   - Content folders and the JSON inside them, and the Founder's tool that searches roles and squads.
   - The conformance test (IF-1.3) must pass.
5. **Web app** `[web]`
   - Folder, components, strings and CSS class names.
   - Page title, the manifest and app name, and any `localStorage` keys.
   - Regenerate `web/openapi.json` and the API client.
6. **Tests** `[tests]`
   - The `Crew` harness becomes `Squad`, along with test helpers and variable names.
   - Tests named after a requirement keep their ids; `docs/traceability.csv` paths are updated where a test file or name changes.
7. **Docs** `[docs]`
   - README, HANDOVER, SECURITY, CLAUDE.md, PLAN, `docs/design`, `content/README.md`, `acceptance/`, `ci/` and `scripts/`.
   - Rename the six `*crew*` screenshots. Images that show the old name on screen are retaken in the next visual pass rather than edited.
8. **Guard** `[NFR-21]`
   - Add a unit test that fails if `crewmind` or whole-word `crew` appears in a tracked file outside an allowlist (spec CHANGELOG, ADR-0008, `docs/phases/`, this plan). This stops the old names drifting back in.
9. **Verify before each push**
   - `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
   - `uv run pytest --db=sqlite` and `--db=postgres`.
   - `npm run build` and the web tests.
   - A fresh `squad setup --slim` and `squad up --slim` smoke run.

## Decisions for the owner

1. **CLI command.**
   - `ns` is not a standard Linux command, but it is taken in practice. The NativeScript CLI (npm, v9.1.2) installs `ns`, and the ns-2 network simulator's binary is `ns`.
   - `squad` collides only with Linaro's SQUAD, a CI quality dashboard on PyPI that installs a `squad` command. That is a narrower audience.
   - Recommendation: `squad` as the command, plus `nightsquad` as a second name that always works.
2. **Existing installs.** The product is a release candidate. Recommendation: rename cleanly with no long-lived aliases, plus three one-time bridges:
   - the 0017 migration that renames the table and converts stored event types;
   - import that still accepts files exported with the old `crewmind_*` markers;
   - `squad doctor` that warns when it finds `CREWMIND_*` variables or a `/var/lib/crewmind` state root, and says how to move them.

   Existing tokens stop working because their prefix changes, so people sign in again and MCP clients get new tokens. The alternative is to accept both prefixes for one release.
3. **Outside the repository** (owner's actions):
   - rename the GitHub repository;
   - register nightsquad.dev and nightsquad.ai;
   - reserve `nightsquad` on PyPI and npm;
   - check that github.com/nightsquad is free.
