#!/usr/bin/env bash
# Starts a throwaway Nightsquad server for the end-to-end tests.
#   e2e/start-backend.sh [port] [run directory]
# It uses the mock model (no paid calls, no network), serves web/dist on the same origin,
# and writes setup.json (with the admin's setup link) and server.pid into the run directory.
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_DIR="$(cd "$WEB_DIR/.." && pwd)"
PORT="${1:-8455}"
RUN_DIR="${2:-$WEB_DIR/e2e/.run}"

if [ -f "$RUN_DIR/server.pid" ]; then
  "$WEB_DIR/e2e/stop-backend.sh" "$RUN_DIR" || true
fi
rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR/scripts"
cat > "$RUN_DIR/scripts/CEO.chat.json" <<'JSON'
[{"text": "Here is the **plan**:\n\n1. Research\n2. Draft\n\n```python\nprint(1)\n```"}]
JSON

export NIGHTSQUAD_DATA_DIR="$RUN_DIR/data"
export NIGHTSQUAD_PORT="$PORT"
export NIGHTSQUAD_API="http://127.0.0.1:$PORT"
export NIGHTSQUAD_SANDBOX_MODE=unisolated
export NIGHTSQUAD_MOCK_SCRIPT_DIR="$RUN_DIR/scripts"
# Recall memory runs in the server process: no model files and no network.
export NIGHTSQUAD_MEMORY_ENGINE=in-process

cd "$REPO_DIR"
uv run -q squad setup --slim --admin-email dom@example.com --json > "$RUN_DIR/setup.json"
nohup uv run -q squad up --slim > "$RUN_DIR/up.log" 2>&1 &
echo $! > "$RUN_DIR/server.pid"

for _ in $(seq 1 120); do
  if curl -fs "http://127.0.0.1:$PORT/readyz" > /dev/null 2>&1; then
    echo "Nightsquad is ready at http://127.0.0.1:$PORT (run directory: $RUN_DIR)"
    exit 0
  fi
  sleep 0.5
done
echo "Nightsquad did not become ready; see $RUN_DIR/up.log" >&2
exit 1
