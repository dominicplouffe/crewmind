#!/usr/bin/env bash
#
# restore_single_server.sh: put a backup back (NFR-4).
#
# It replaces the database, the master key and the artifacts with the archive's. What
# is there now is saved first, into <state root>/backups/. The server is stopped while
# it runs.
#
# Usage:
#   deploy/restore_single_server.sh <archive>
#
set -euo pipefail

ARCHIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
    *) ARCHIVE="$1"; shift ;;
  esac
done
[ -n "$ARCHIVE" ] || { echo "usage: $0 <archive>" >&2; exit 2; }
[ -f "$ARCHIVE" ] || { echo "no such file: $ARCHIVE" >&2; exit 2; }
ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"

cd "$(dirname "$0")/.."
. deploy/_common.sh

say "Checking where we are"
require_repo_root; ok "in the repository root ($REPO)"
resolve_docker;    ok "docker is usable ($DOCKER)"
load_env

# NFR-4: a restore replaces everything, so it needs the word typed, every time.
printf '\n  This replaces the database, the master key and the artifacts with the backup.\n'
printf '  What is there now is saved first. crewmind stops while it runs.\n\n'
printf '  Type restore to confirm: '
read -r reply
[ "$reply" = "restore" ] || die "not confirmed: nothing was changed"

say "Stopping the server"
compose stop server >/dev/null || die "could not stop the server"
ok "stopped"

say "Restoring"
# A one-off container of the server image, with the archive mounted where it can read it.
if out="$(compose run --rm --no-deps -T -v "$ARCHIVE:/restore.tar.gz:ro" server \
          crewmind restore --archive /restore.tar.gz --confirm restore 2>&1)"; then
  printf '%s\n' "$out" | sed 's/^/    /'
else
  compose up -d >/dev/null 2>&1 || true
  die "the restore failed, and the server was started again on what it had:
$out"
fi

say "Starting the server"
compose up -d --no-build >/dev/null || die "compose up failed"
wait_for_server 300
ok "crewmind is back, on the restored data: $PUBLIC_URL"
