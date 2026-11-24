# ADR-0009: Shell scripts run the Docker install

- **Status:** Accepted (22 Nov 2026, owner: Dominic)
- **Spec:** NFR-1, NFR-2, NFR-3, NFR-4, NFR-24

## Context

A full server runs in Docker. Something on the host has to write the settings file, build the images, start the services, wait for them and call the server's own setup. v1 did this with bash scripts in `deploy/`, and the owner asked for the same here.

NFR-24 requires Python for the server, runners, scheduler, gateway, memory, harness loop, CLI and MCP server. A host install script is none of these. `CLAUDE.md` said the web app was the only non-Python code.

## Decision

The Docker install is driven by bash scripts in `deploy/`, named as in v1: `deploy_single_server.sh`, `update_single_server.sh`, `backup_single_server.sh`, `restore_single_server.sh` and `kill_single_server.sh`, with shared helpers in `_common.sh`.

The scripts hold no rule of the product. Setting up, backing up, restoring and checking are the server's own operations (`squad setup`, `backup`, `restore`, `doctor`), which the scripts call inside the server container. The scripts only do what must happen outside it: Docker, the settings file, git.

## Consequences

- A host needs only Docker, bash, `openssl` and `curl` to install: no Python and no `uv`.
- The scripts are not covered by the Python test suite, ruff or pyright. They were run by hand; a change to one must be run by hand again.
- `CLAUDE.md` now names `deploy/` as the second place with non-Python code.
