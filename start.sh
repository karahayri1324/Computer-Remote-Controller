#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/agent"

# Check config exists
if [ ! -f "$AGENT_DIR/config.yaml" ]; then
    echo "Config not found. Run ./setup.sh first."
    exit 1
fi

echo "Starting RemoteController Agent..."
echo "Press Ctrl+C to stop."
echo ""

cd "$AGENT_DIR"
python3 main.py
