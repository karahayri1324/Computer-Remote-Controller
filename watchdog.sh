#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$SCRIPT_DIR/watchdog.log"

while true; do
    if ! pgrep -f "python3 main.py" > /dev/null 2>&1 && ! pgrep -f "$SCRIPT_DIR/start.sh" > /dev/null 2>&1; then
        echo "[$(date '+%F %T')] main.py down, restarting..." >> "$LOG"
        cd "$SCRIPT_DIR"
        nohup ./start.sh >> "$SCRIPT_DIR/start.log" 2>&1 &
        sleep 5
    fi
    sleep 10
done
