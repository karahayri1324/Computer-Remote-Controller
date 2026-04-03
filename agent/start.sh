#!/bin/bash
cd "$(dirname "$0")"
pip3 install -r requirements.txt -q 2>/dev/null
nohup python3 main.py > agent.log 2>&1 &
echo "Agent started (PID: $!)"
