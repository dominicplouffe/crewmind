#!/usr/bin/env bash
# Stops the server that start-backend.sh started.
#   e2e/stop-backend.sh [run directory]
set -uo pipefail
WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="${1:-$WEB_DIR/e2e/.run}"
[ -f "$RUN_DIR/server.pid" ] || exit 0
PID="$(cat "$RUN_DIR/server.pid")"
pkill -TERM -P "$PID" 2> /dev/null
kill -TERM "$PID" 2> /dev/null
rm -f "$RUN_DIR/server.pid"
exit 0
