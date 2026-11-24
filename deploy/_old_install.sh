# Carries a Docker install from before the product was renamed (ADR-0011) onto the new
# names. Sourced by deploy_single_server.sh and update_single_server.sh after _common.sh,
# never run on its own. Every step can be repeated, and nothing is deleted: the old
# volumes stay as they were until you remove them by hand.
#
# What changed name:
#   - the variables in deploy/.env;
#   - the Compose project, and with it the volumes of the database and the TLS front;
#   - the database's role and the database itself;
#   - the sandbox label.
#
# shellcheck shell=bash

OLD_NAME="crew""mind"
OLD_PREFIX="$(printf '%s' "$OLD_NAME" | tr '[:lower:]' '[:upper:]')_"
NEW_NAME="nightsquad"
NEW_NAME_PREFIX="NIGHTSQUAD_"
OLD_LABEL="$OLD_NAME.install"
HELPER_ROLE="rename_helper"
DATABASE_IMAGE="pgvector/pgvector:pg17"   # deploy/compose.yaml's database image

old_containers() {
  $DOCKER ps -aq --filter "label=com.docker.compose.project=$OLD_NAME" 2>/dev/null || true
}

volume_exists() { $DOCKER volume inspect "$1" >/dev/null 2>&1; }

# Set while a carry runs, so a run that stops halfway is finished by the next one.
IN_PROGRESS="deploy/.rename-in-progress"

# Anything left under the old name: variables, containers or volumes, or a carry that
# did not finish.
old_install_found() {
  [ -e "$IN_PROGRESS" ] && return 0
  { [ -f "$ENV_FILE" ] && grep -q "^$OLD_PREFIX" "$ENV_FILE"; } && return 0
  [ -n "$(old_containers)" ] && return 0
  volume_exists "${OLD_NAME}_database" && ! volume_exists "${NEW_NAME}_database"
}

# Through the old server, while it still runs: the new scripts reach only the new project.
_backup_through_old_server() {
  local id out
  id="$($DOCKER ps -q --filter "label=com.docker.compose.project=$OLD_NAME" \
        --filter "label=com.docker.compose.service=server" | head -n 1)"
  if [ -z "$id" ]; then
    warn "the old server is not running: no backup taken through it"
    return 0
  fi
  out="$($DOCKER exec "$id" "$OLD_NAME" backup)" \
    || die "the backup through the old server failed; nothing was changed
$out"
  ok "backed up: $(printf '%s\n' "$out" | sed -n 's/^archive: //p')"
}

# deploy/.env: every old variable under its new name. A new name already set wins.
_rename_variables() {
  if ! { [ -f "$ENV_FILE" ] && grep -q "^$OLD_PREFIX" "$ENV_FILE"; }; then
    ok "deploy/.env has no old names"
    return 0
  fi
  cp -p "$ENV_FILE" "$ENV_FILE.before-rename"
  chmod 600 "$ENV_FILE.before-rename"
  local line name value
  while IFS= read -r line; do
    name="${line%%=*}"; value="${line#*=}"
    [ -n "$(env_get "$NEW_NAME_PREFIX${name#"$OLD_PREFIX"}")" ] \
      || env_set "$NEW_NAME_PREFIX${name#"$OLD_PREFIX"}" "$value"
  done < <(grep "^$OLD_PREFIX" "$ENV_FILE")
  local tmp
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  grep -v "^$OLD_PREFIX" "$ENV_FILE" > "$tmp" || true
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
  ok "deploy/.env uses the new names (the old file is deploy/.env.before-rename)"
}

# The old project's containers, its network and its sandboxes. Volumes are kept.
_stop_old_project() {
  local ids
  ids="$(old_containers)"
  if [ -n "$ids" ]; then
    # shellcheck disable=SC2086
    $DOCKER rm -f $ids >/dev/null
    ok "stopped and removed the old project's containers"
  fi
  ids="$($DOCKER ps -aq --filter "label=$OLD_LABEL" || true)"
  # shellcheck disable=SC2086
  [ -z "$ids" ] || { $DOCKER rm -f $ids >/dev/null && ok "removed the old sandbox containers"; }
  ids="$($DOCKER network ls -q --filter "label=$OLD_LABEL" || true)"
  # shellcheck disable=SC2086
  [ -z "$ids" ] || $DOCKER network rm $ids >/dev/null 2>&1 || true
  $DOCKER network rm "${OLD_NAME}_default" >/dev/null 2>&1 || true
}

# A copy of each old volume under the project's new name, labelled as Compose labels its own.
_copy_volumes() {
  local volume from to
  for volume in database proxy; do
    from="${OLD_NAME}_$volume"; to="${NEW_NAME}_$volume"
    if ! volume_exists "$from"; then
      continue
    elif volume_exists "$to"; then
      ok "$to already exists; $from left as it is"
      continue
    fi
    $DOCKER volume create \
      --label "com.docker.compose.project=$NEW_NAME" \
      --label "com.docker.compose.volume=$volume" "$to" >/dev/null \
      || die "could not create the volume $to"
    $DOCKER run --rm -v "$from:/from:ro" -v "$to:/to" --entrypoint sh "$DATABASE_IMAGE" \
      -c 'cp -a /from/. /to/' \
      || { $DOCKER volume rm "$to" >/dev/null 2>&1; die "copying $from to $to failed; $from is unchanged"; }
    ok "copied $from to $to"
  done
}

# Inside the database container, over its local socket, which needs no password.
_sql() {
  local role="$1"; shift
  compose exec -T database psql -v ON_ERROR_STOP=1 -qAt -U "$role" -d postgres "$@"
}

_role_exists() {
  local as="$1" role="$2"
  [ "$(_sql "$as" -c "SELECT 1 FROM pg_roles WHERE rolname = '$role'" 2>/dev/null)" = "1" ]
}

# The role and the database take the new name. A role cannot rename itself, so a helper
# role does it and is dropped after. The password is set again: renaming clears an MD5 one.
_rename_database() {
  if ! volume_exists "${NEW_NAME}_database"; then
    return 0
  fi
  compose up -d database >/dev/null || die "the database did not start"
  local waited=0
  until compose exec -T database pg_isready -q >/dev/null 2>&1; do
    waited=$((waited + 2))
    [ "$waited" -lt 120 ] || die "the database was not ready after 120s"
    sleep 2
  done
  if _role_exists "$NEW_NAME" "$NEW_NAME" && ! _role_exists "$NEW_NAME" "$OLD_NAME"; then
    ok "the database already uses the new names"
    return 0
  fi
  _role_exists "$OLD_NAME" "$OLD_NAME" || die "the database has neither the old role nor the new one"
  local password
  password="$(env_get "${NEW_NAME_PREFIX}DB_PASSWORD")"
  [ -n "$password" ] || die "deploy/.env has no ${NEW_NAME_PREFIX}DB_PASSWORD"
  _sql "$OLD_NAME" >/dev/null <<SQL || die "renaming the database failed; the old volume is unchanged"
SET client_min_messages = warning;
DROP ROLE IF EXISTS $HELPER_ROLE;
CREATE ROLE $HELPER_ROLE SUPERUSER LOGIN;
SELECT 'ALTER DATABASE $OLD_NAME RENAME TO $NEW_NAME'
  WHERE EXISTS (SELECT 1 FROM pg_database WHERE datname = '$OLD_NAME') \gexec
SQL
  _sql "$HELPER_ROLE" >/dev/null <<SQL || die "renaming the database role failed"
SELECT 'ALTER ROLE $OLD_NAME RENAME TO $NEW_NAME'
  WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$OLD_NAME') \gexec
ALTER ROLE $NEW_NAME PASSWORD '$password';
SQL
  _sql "$NEW_NAME" -c "DROP ROLE $HELPER_ROLE" >/dev/null || warn "the helper role $HELPER_ROLE is left"
  ok "the database and its role are named $NEW_NAME"
}

# The whole carry, or (with "dry") what it would do.
carry_old_install() {
  local mode="${1:-run}" backup="${2:-yes}"
  old_install_found || return 0
  say "Install from before the rename"
  if [ "$mode" = "dry" ]; then
    echo "  would back up through the old server, rename the variables in deploy/.env,"
    echo "  stop the old project's containers, copy its volumes under the new name, and"
    echo "  rename the database and its role. The old volumes would be kept."
    return 0
  fi
  touch "$IN_PROGRESS"
  if [ "$backup" = "yes" ]; then
    _backup_through_old_server
  else
    warn "no backup taken (--no-backup)"
  fi
  _rename_variables
  _stop_old_project
  _copy_volumes
  _rename_database
  rm -f "$IN_PROGRESS"
  cat <<EOF
    The old volumes ${OLD_NAME}_database and ${OLD_NAME}_proxy are unchanged. Once the
    new install has run well for a while, remove them with:
      $DOCKER volume rm ${OLD_NAME}_database ${OLD_NAME}_proxy
EOF
}
