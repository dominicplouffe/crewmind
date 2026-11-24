#!/usr/bin/env bash
#
# update_single_server.sh: pull new code and bring the running install onto it (NFR-3).
#
# It refuses a checkout with local edits, backs up first, rebuilds both images, restarts,
# and waits until the server is ready. Migrations need no step of their own: the server
# applies them when it starts, and it is not ready until the schema is current.
#
# An install from before the product was renamed is carried onto the new names first
# (deploy/_old_install.sh). For that one update, pull by hand and run this with
# --no-pull: the script that starts the pull is the old one.
#
# Usage:
#   deploy/update_single_server.sh               # pull, back up, rebuild, restart
#   deploy/update_single_server.sh --no-pull     # rebuild what is already checked out
#   deploy/update_single_server.sh --no-backup   # skip the backup (not advised)
#   deploy/update_single_server.sh --dry-run     # say what would happen, change nothing
#
set -euo pipefail

PULL="yes"; BACKUP="yes"; DRY="no"
while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull)   PULL="no"; shift ;;
    --no-backup) BACKUP="no"; shift ;;
    --dry-run)   DRY="yes"; shift ;;
    -h|--help)   sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
. deploy/_common.sh
. deploy/_old_install.sh

say "Checking where we are"
require_repo_root; ok "in the repository root ($REPO)"
resolve_docker;    ok "docker is usable ($DOCKER)"
carry_old_install "$([ "$DRY" = "yes" ] && echo dry || echo run)" "$BACKUP"
load_env;          ok "deploy/.env read"

# ── 1. new code ───────────────────────────────────────────────────────────────
say "Code"
if [ "$PULL" = "no" ]; then
  warn "skipping git pull (--no-pull)"
elif [ ! -d .git ]; then
  warn "not a git checkout: nothing to pull"
else
  # A pull over local edits is how edits get lost or a conflict lands mid-update.
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short --untracked-files=no | sed 's/^/      /'
    die "the checkout has uncommitted changes. Commit or stash them, or use --no-pull."
  fi
  if [ "$DRY" = "yes" ]; then
    git fetch --quiet || die "git fetch failed"
    behind="$(git rev-list --count 'HEAD..@{upstream}' 2>/dev/null || echo '?')"
    ok "would pull $behind new commit(s)"
  else
    before="$(git rev-parse HEAD)"
    git pull --ff-only || die "git pull failed (not a fast-forward?). Resolve it, then run again."
    after="$(git rev-parse HEAD)"
    if [ "$before" = "$after" ]; then
      ok "already up to date ($(git rev-parse --short HEAD))"
    else
      ok "updated $(git rev-parse --short "$before") -> $(git rev-parse --short "$after")"
      git log --oneline "$before..$after" | sed 's/^/      /'
    fi
  fi
fi

if [ "$DRY" = "yes" ]; then
  say "Dry run"
  [ "$BACKUP" = "no" ] || echo "  would back up the database, the master key and the artifacts"
  echo "  would rebuild the server image and the agent image, restart, and wait until ready"
  echo "  Nothing was changed."
  exit 0
fi

# ── 2. backup ─────────────────────────────────────────────────────────────────
# Before the new code migrates anything: a migration that applies cleanly and turns out
# wrong is still one you want to undo.
say "Backup"
if [ "$BACKUP" = "no" ]; then
  warn "skipped (--no-backup)"
elif ! server_is_running; then
  warn "the server is not running: nothing to back up through it"
else
  out="$(squad backup)" || die "the backup failed; nothing was updated (override with --no-backup)
$out"
  ok "$(printf '%s\n' "$out" | sed -n 's/^archive: //p')"
fi

# ── 3. images and restart ─────────────────────────────────────────────────────
say "Images"
build_images; ok "built the server image and the agent image"
say "Services"
compose up -d --no-build --remove-orphans || die "compose up failed"
ok "restarted on the new code"

# ── 4. ready, on the current schema ───────────────────────────────────────────
say "Waiting for the server"
wait_for_server 300
ok "ready: the database answers and its schema is current"
squad setup >/dev/null || warn "squad setup reported a problem; run it by hand to see"

say "Done"
cat <<EOF
  nightsquad is at $PUBLIC_URL on $(git rev-parse --short HEAD 2>/dev/null || echo 'the new code').
  To undo, restore the backup above: deploy/restore_single_server.sh <archive>
EOF
