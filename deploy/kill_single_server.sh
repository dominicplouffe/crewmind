#!/usr/bin/env bash
#
# kill_single_server.sh: stop crewmind on this machine.
#
# By default it stops and removes the containers and KEEPS your data: the database
# volume, deploy/.env and the state directory (master key, artifacts, workspaces) all
# stay, so deploy/deploy_single_server.sh brings the same install back.
#
# It also removes the sandbox containers the server started. Those are siblings, not
# compose services, so `docker compose down` alone leaves them behind.
#
# Usage:
#   deploy/kill_single_server.sh               # stop everything, keep the data
#   deploy/kill_single_server.sh --wipe        # ALSO destroy the database (asks first)
#   deploy/kill_single_server.sh --sandboxes   # only remove leftover sandbox containers
#
set -euo pipefail

WIPE="no"; ONLY_SANDBOXES="no"
while [ $# -gt 0 ]; do
  case "$1" in
    --wipe)      WIPE="yes"; shift ;;
    --sandboxes) ONLY_SANDBOXES="yes"; shift ;;
    -h|--help)   sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
. deploy/_common.sh

say "Checking where we are"
require_repo_root; ok "in the repository root ($REPO)"
resolve_docker;    ok "docker is usable ($DOCKER)"
load_env

say "Sandbox containers"
remove_sandboxes
if [ "$ONLY_SANDBOXES" = "yes" ]; then
  say "Done"
  echo "  The server was left running (--sandboxes)."
  exit 0
fi

if [ "$WIPE" = "yes" ]; then
  say "Destroying the database"
  warn "--wipe removes the Postgres volume: every project, run, decision, memory and"
  warn "stored key in it. There is no undo. $STATE_ROOT is left as it is."
  # NFR-4: a destructive wipe needs a typed confirmation word, every time.
  printf '\n    Type DESTROY to confirm: '
  read -r reply
  [ "$reply" = "DESTROY" ] || die "not confirmed: nothing was wiped (the sandboxes above were still removed)"
  compose down -v || die "compose down -v failed"
  ok "the containers and the database volume are gone"
else
  say "Stopping"
  compose down || die "compose down failed"
  ok "containers removed; the database volume and $STATE_ROOT are intact"
fi

say "Done"
echo "  Start it again with: deploy/deploy_single_server.sh"
