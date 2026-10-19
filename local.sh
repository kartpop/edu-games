#!/usr/bin/env bash
# Serve the games on the home Wi-Fi so an iPhone/iPad can open them.
# usage: ./local.sh up | down | status
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8080}"
PIDFILE=.local-server.pid
LOG=.local-server.log

ip_addr() { ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo localhost; }
running() { [[ -f $PIDFILE ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

show_urls() {
  local ip; ip=$(ip_addr)
  echo
  echo "  This Mac:     http://localhost:$PORT/"
  echo "  iPhone/iPad:  http://$ip:$PORT/   (same Wi-Fi)"
  echo
  for d in games/*/*/; do
    [[ -f "$d/index.html" ]] && echo "  ${d%/}  →  http://$ip:$PORT/$d"
  done
  echo
}

case "${1:-status}" in
  up)
    if running; then
      echo "Already running (pid $(cat "$PIDFILE"))."
    else
      if lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "Port $PORT is busy. Try: PORT=8090 $0 up"; exit 1
      fi
      nohup python3 -m http.server "$PORT" --bind 0.0.0.0 >"$LOG" 2>&1 &
      echo $! >"$PIDFILE"
      sleep 0.5
      running || { echo "Server did not start, see $LOG"; rm -f "$PIDFILE"; exit 1; }
      echo "Started (pid $(cat "$PIDFILE"))."
    fi
    show_urls
    ;;
  down)
    if running; then kill "$(cat "$PIDFILE")"; echo "Stopped."; else echo "Not running."; fi
    rm -f "$PIDFILE"
    ;;
  status)
    if running; then echo "Running (pid $(cat "$PIDFILE"))."; show_urls; else echo "Not running."; fi
    ;;
  *)
    echo "usage: $0 up | down | status"; exit 1
    ;;
esac
