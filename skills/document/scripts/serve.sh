#!/bin/sh
# Serve published HTML reports from the remote host so they can be opened
# directly in a local browser.
#
#   sh skills/document/scripts/serve.sh          # start on port 8899
#   sh skills/document/scripts/serve.sh 8900     # start on a different port
#   sh skills/document/scripts/serve.sh stop     # stop the running server
#
# Then open:  http://<remote-host>:<port>/
set -e

PORT="${1:-8899}"
# scripts/ -> document/ -> skills/ -> workspace root
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/reports"
PIDFILE="$ROOT/.skillsearch/serve.pid"
LOG="$ROOT/.skillsearch/serve.log"

mkdir -p "$(dirname "$PIDFILE")"

if [ "$PORT" = "stop" ]; then
  if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "stopped"
  else
    echo "no pidfile; nothing to stop"
  fi
  exit 0
fi

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running (pid $(cat "$PIDFILE"))"
  exit 0
fi

if [ ! -d "$OUT" ]; then
  echo "reports/ missing; run publish.py first" >&2
  exit 1
fi

nohup python3 -m http.server "$PORT" --directory "$OUT" > "$LOG" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

HOST="$(hostname)"
echo "serving $OUT on port $PORT (pid $(cat "$PIDFILE"))"
echo "open: http://$HOST:$PORT/"
