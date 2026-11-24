#!/usr/bin/env bash
#
# backup_single_server.sh: everything this install cannot rebuild, in one file (NFR-4).
#
# The archive holds the database, the master key that opens every stored secret, and the
# artifacts. It is written readable by its owner alone. Copy it off this machine: a
# backup on the same disk does not survive the disk.
#
# Usage:
#   deploy/backup_single_server.sh                       # into <state root>/backups/
#   deploy/backup_single_server.sh --out /mnt/nas/nightsquad.tar.gz
#
set -euo pipefail

OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="${2:?--out needs a path}"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done
[ -z "$OUT" ] || OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

cd "$(dirname "$0")/.."
. deploy/_common.sh

say "Checking where we are"
require_repo_root; ok "in the repository root ($REPO)"
resolve_docker;    ok "docker is usable ($DOCKER)"
load_env
server_is_running || die "the server is not running. Start it: deploy/deploy_single_server.sh"

say "Backup"
out="$(squad backup)" || die "the backup failed:
$out"
archive="$(printf '%s\n' "$out" | sed -n 's/^archive: //p')"
[ -n "$archive" ] || die "the server did not say where it wrote the archive:
$out"
if [ -n "$OUT" ]; then
  # Read through the server, so this works when the state directory is root's.
  ( umask 077; compose exec -T server cat "$archive" > "$OUT" ) || die "could not write $OUT"
  compose exec -T server rm -f "$archive"
  archive="$OUT"
fi
ok "$archive"

say "Done"
cat <<EOF
  This file holds your master key. Keep it like a password, and off this machine.
  Restore with: deploy/restore_single_server.sh $archive
EOF
