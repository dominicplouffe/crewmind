#!/usr/bin/env bash
#
# deploy_single_server.sh: take a machine with Docker to a running nightsquad, or bring an
# existing install up on the code that is checked out (NFR-1, NFR-2, NFR-6). Safe to run
# again: it never replaces a secret, and it keeps the address it was last given.
#
# Everything runs here in Docker: Postgres, the server, a TLS front, and one container
# per agent run.
#
# Usage:
#   deploy/deploy_single_server.sh --admin-email you@example.com   # first install
#   deploy/deploy_single_server.sh                       # this machine only: https://localhost
#   deploy/deploy_single_server.sh --bind 192.168.1.50   # reach it at https://192.168.1.50
#   deploy/deploy_single_server.sh --bind 0.0.0.0 --public-url https://squad.example.com \
#                                  --tls you@example.com # a public name, real certificate
#   deploy/deploy_single_server.sh --port 8443           # another TLS port
#   deploy/deploy_single_server.sh --state-root ~/nightsquad-data
#   deploy/deploy_single_server.sh --no-build            # use the images already here
#
set -euo pipefail

BIND=""; PUBLIC_URL_ARG=""; PORT=""; TLS=""; STATE_ROOT_ARG=""; ADMIN_EMAIL=""; BUILD="yes"
while [ $# -gt 0 ]; do
  case "$1" in
    --bind)        BIND="${2:?--bind needs an address}"; shift 2 ;;
    --public-url)  PUBLIC_URL_ARG="${2:?--public-url needs an https address}"; shift 2 ;;
    --port)        PORT="${2:?--port needs a port}"; shift 2 ;;
    --tls)         TLS="${2:?--tls needs 'internal' or an email address}"; shift 2 ;;
    --state-root)  STATE_ROOT_ARG="${2:?--state-root needs a directory}"; shift 2 ;;
    --admin-email) ADMIN_EMAIL="${2:?--admin-email needs an address}"; shift 2 ;;
    --no-build)    BUILD="no"; shift ;;
    -h|--help)     sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
. deploy/_common.sh

# ── 1. preflight ──────────────────────────────────────────────────────────────
say "Checking where we are and what we have"
require_repo_root; ok "in the repository root ($REPO)"
resolve_docker;    ok "docker is usable ($DOCKER)"
command -v openssl >/dev/null 2>&1 || die "openssl is missing (it makes the database password).
    sudo apt-get install -y openssl"
command -v curl >/dev/null 2>&1 || die "curl is missing.
    sudo apt-get install -y curl"

# ── 2. where people reach it ──────────────────────────────────────────────────
# People sign in over TLS at one address, the public URL, and nowhere else (NFR-6).
# A bare re-run keeps what the last run chose.
say "Address"
ASKED="${BIND}${PORT}"           # set when this run names an address or a port
BIND="${BIND:-$(env_get NIGHTSQUAD_BIND)}";  BIND="${BIND:-127.0.0.1}"
TLS="${TLS:-$(env_get NIGHTSQUAD_TLS)}";     TLS="${TLS:-internal}"
PORT="${PORT:-$(env_get NIGHTSQUAD_TLS_PORT)}"; PORT="${PORT:-443}"
KEPT_URL="$(env_get NIGHTSQUAD_PUBLIC_URL)"
case "$BIND" in
  127.0.0.1) host="localhost" ;;
  0.0.0.0)   host="" ;;
  *)         host="$BIND" ;;
esac
suffix=""; [ "$PORT" = "443" ] || suffix=":$PORT"
if [ -n "$PUBLIC_URL_ARG" ]; then
  PUBLIC_URL="$PUBLIC_URL_ARG"
elif [ -n "$KEPT_URL" ] && [ -z "$ASKED" ]; then
  PUBLIC_URL="$KEPT_URL"
elif [ -n "$host" ]; then
  PUBLIC_URL="https://${host}${suffix}"
else
  PUBLIC_URL=""
fi
[ -n "$PUBLIC_URL" ] || die "--bind 0.0.0.0 listens on every address, so say which one people
    will type: --public-url https://<name or address>"
PUBLIC_URL="${PUBLIC_URL%/}"
case "$PUBLIC_URL" in
  https://*) ;;
  *) die "--public-url must start with https:// (got $PUBLIC_URL). People sign in only over TLS." ;;
esac
hostport="${PUBLIC_URL#https://}"
case "$hostport" in */*) die "--public-url must have no path (got $PUBLIC_URL)" ;; esac
PUBLIC_HOST="${hostport%%:*}"
case "$hostport" in *:*) PORT="${hostport##*:}" ;; *) PORT="443" ;; esac
ok "people sign in at $PUBLIC_URL"
if [ "$BIND" = "127.0.0.1" ]; then
  ok "listening on this machine only (127.0.0.1:$PORT)"
else
  warn "listening on ${BIND}:${PORT}: anyone who can reach that address can reach the sign-in page."
  warn "Docker's own firewall rules sit in front of ufw, so this really is reachable."
fi
if [ "$TLS" = "internal" ]; then
  ok "the TLS front signs its own certificate; a browser asks once to accept it"
else
  ok "the TLS front gets a certificate from Let's Encrypt for $PUBLIC_HOST (contact: $TLS)"
fi

# ── 3. settings and secrets (deploy/.env) ─────────────────────────────────────
say "Settings (deploy/.env)"
STATE_ROOT="${STATE_ROOT_ARG:-$(env_get NIGHTSQUAD_STATE_ROOT)}"
STATE_ROOT="${STATE_ROOT:-/var/lib/nightsquad}"
if [ -n "$(env_get NIGHTSQUAD_DB_PASSWORD)" ]; then
  ok "the database password is already set; left untouched"
else
  env_set NIGHTSQUAD_DB_PASSWORD "$(openssl rand -hex 24)"
  ok "made a database password"
fi
env_set NIGHTSQUAD_STATE_ROOT "$STATE_ROOT"
env_set NIGHTSQUAD_PUBLIC_URL "$PUBLIC_URL"
env_set NIGHTSQUAD_PUBLIC_HOST "$PUBLIC_HOST"
env_set NIGHTSQUAD_BIND "$BIND"
env_set NIGHTSQUAD_TLS_PORT "$PORT"
env_set NIGHTSQUAD_TLS "$TLS"
ok "written (readable by you only)"

# ── 4. host directory ─────────────────────────────────────────────────────────
# Sandboxes are sibling containers, so a workspace path must mean the same thing on the
# host and inside the server. The master key is made here by the server, once.
say "Host directory"
if [ -d "$STATE_ROOT" ]; then
  ok "$STATE_ROOT exists"
else
  { mkdir -p "$STATE_ROOT" 2>/dev/null || sudo mkdir -p "$STATE_ROOT"; } && ok "created $STATE_ROOT"
fi

# ── 5. images and services ────────────────────────────────────────────────────
say "Images"
if [ "$BUILD" = "yes" ]; then
  build_images; ok "built the server image and the agent image"
else
  warn "skipped (--no-build): using the images already on this machine"
fi
say "Services"
compose up -d --no-build --remove-orphans || die "compose up failed"
ok "started"

# ── 6. wait until ready ───────────────────────────────────────────────────────
say "Waiting for the server"
wait_for_server 300
ok "ready: the database answers and its schema is current"

# ── 7. the first admin and the starter libraries ──────────────────────────────
# The server's own setup does this, and does nothing when it is already done.
say "Setup"
setup=(setup)
[ -z "$ADMIN_EMAIL" ] || setup+=(--admin-email "$ADMIN_EMAIL")
SETUP_OUT="$(nightsquad "${setup[@]}")" || die "squad setup failed: $SETUP_OUT"
printf '%s\n' "$SETUP_OUT" | grep -E '^\s+- ' | sed 's/^ *- /    /'
LINK="$(printf '%s\n' "$SETUP_OUT" | sed -n 's/^setup_link: //p')"

# ── 8. check ──────────────────────────────────────────────────────────────────
say "Checking the install"
if DOCTOR_OUT="$(squad doctor)"; then :; fi
printf '%s\n' "$DOCTOR_OUT" | grep -E 'ok=False' | sed 's/^ *- /    ! /' || ok "doctor finds nothing wrong"

say "Running"
cat <<EOF
  nightsquad is at $PUBLIC_URL
EOF
if [ -n "$LINK" ]; then
  cat <<EOF

  Set your password here (the link works once):
      $LINK
EOF
elif printf '%s\n' "$SETUP_OUT" | grep -q "No admin yet"; then
  cat <<EOF

  Nobody can sign in yet. Make the first admin:
      deploy/deploy_single_server.sh --admin-email you@example.com
EOF
fi
cat <<EOF

  Back up $STATE_ROOT/master.key off this machine: without it no stored
  model key can be read. deploy/backup_single_server.sh saves everything in one file.

  The squad command runs inside the server:
      (cd deploy && $DOCKER compose exec server squad --help)

  Update: deploy/update_single_server.sh      Stop: deploy/kill_single_server.sh
EOF
