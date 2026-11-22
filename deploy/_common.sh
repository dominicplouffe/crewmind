# Shared by the deploy/*_single_server.sh scripts. Sourced, never run on its own.
#
# shellcheck shell=bash

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mFAILED:\033[0m %s\n\n' "$*" >&2; exit 1; }

on_interrupt() {
  printf '\n'
  warn "interrupted. Running the script again is safe: every step can be repeated."
  exit 130
}
trap on_interrupt INT TERM

ENV_FILE="deploy/.env"
SERVER_PORT=8420            # the server's plain port, published on 127.0.0.1 only
AGENT_IMAGE="crewmind-agent"
INSTALL_LABEL="crewmind.install"

# The checkout root, judged by the files these scripts need.
require_repo_root() {
  local marker
  for marker in pyproject.toml deploy/compose.yaml deploy/Dockerfile deploy/agent.Dockerfile; do
    [ -e "$marker" ] \
      || die "no ./$marker here: this script must live in deploy/ of a crewmind checkout (looked in $PWD)"
  done
  REPO="$PWD"
}

# Plain docker if this user may use it, else sudo docker.
resolve_docker() {
  command -v docker >/dev/null 2>&1 || die "docker is not installed. Install it with:
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker \"\$USER\"   # then log out and back in"
  if docker info >/dev/null 2>&1; then
    DOCKER="docker"
  elif sudo -n docker info >/dev/null 2>&1 || sudo docker info >/dev/null 2>&1; then
    DOCKER="sudo docker"
    warn "using 'sudo docker'. To drop the sudo: sudo usermod -aG docker \"\$USER\", then log in again."
  else
    die "the docker daemon does not answer. Is it running? Try: sudo systemctl start docker"
  fi
  $DOCKER compose version >/dev/null 2>&1 \
    || die "the docker compose plugin is missing. On Debian or Ubuntu:
    sudo apt-get install -y docker-compose-plugin"
}

# Every compose call runs from deploy/, so the project name and deploy/.env resolve the
# same way wherever the caller stood.
compose() { ( cd "$REPO/deploy" && $DOCKER compose "$@" ); }

# One value from deploy/.env, or nothing.
env_get() {
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

# Set one value in deploy/.env, replacing an earlier line for the same name.
env_set() {
  local tmp
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  [ -f "$ENV_FILE" ] && { grep -v "^$1=" "$ENV_FILE" > "$tmp" || true; }
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

load_env() {
  [ -f "$ENV_FILE" ] || die "$ENV_FILE is missing. Run deploy/deploy_single_server.sh first."
  STATE_ROOT="$(env_get CREWMIND_STATE_ROOT)"; STATE_ROOT="${STATE_ROOT:-/var/lib/crewmind}"
  PUBLIC_URL="$(env_get CREWMIND_PUBLIC_URL)"; PUBLIC_URL="${PUBLIC_URL:-https://localhost}"
}

server_is_running() {
  compose ps --status running --services 2>/dev/null | grep -q '^server$'
}

# The crewmind command, inside the server container.
crewmind() { compose exec -T server crewmind "$@"; }

# Both images, every time: the agent image is what agent runs execute in, and a stale
# one runs old harness code.
build_images() {
  compose build || die "building the images failed; the output above says why"
}

# Ready means the database answers and its schema is current (NFR-5). Migrations run
# when the server starts, so this is also the check that they applied.
wait_for_server() {
  local seconds="${1:-300}" waited=0
  until curl -fsS -o /dev/null "http://127.0.0.1:${SERVER_PORT}/readyz" 2>/dev/null; do
    waited=$((waited + 2))
    [ "$waited" -lt "$seconds" ] || die "the server was not ready after ${seconds}s. Look at:
    (cd deploy && $DOCKER compose logs server --tail=50)"
    sleep 2
  done
}

# Sandboxes are sibling containers, not compose services, so `compose down` leaves them.
remove_sandboxes() {
  local ids
  ids="$($DOCKER ps -aq --filter "label=$INSTALL_LABEL" || true)"
  if [ -z "$ids" ]; then
    ok "no sandbox containers to remove"
  else
    # shellcheck disable=SC2086
    $DOCKER rm -f $ids >/dev/null
    ok "removed $(echo "$ids" | wc -l | tr -d ' ') sandbox container(s)"
  fi
  ids="$($DOCKER network ls -q --filter "label=$INSTALL_LABEL" || true)"
  # shellcheck disable=SC2086
  [ -z "$ids" ] || $DOCKER network rm $ids >/dev/null 2>&1 || true
}
