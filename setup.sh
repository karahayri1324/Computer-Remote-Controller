#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

clear
echo -e "${BLUE}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║       RemoteController Setup         ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    OS="windows"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
fi
echo -e "${GREEN}OS:${NC} $OS"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/agent"

echo ""
echo -e "${YELLOW}── Connection Settings ──${NC}"
echo ""

# Ask for relay URL
read -p "Relay server URL [wss://rc.thinkerchat.com/ws/agent]: " RELAY_URL
RELAY_URL="${RELAY_URL:-wss://rc.thinkerchat.com/ws/agent}"

# Ask for agent token
echo ""
echo -e "${BLUE}Agent token is the secret key that connects your PC to the relay."
echo -e "Get this from the server admin.${NC}"
echo ""
read -p "Agent token: " AGENT_TOKEN

if [ -z "$AGENT_TOKEN" ]; then
    echo -e "${RED}Error: Agent token cannot be empty.${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}── Installing Dependencies ──${NC}"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed!${NC}"
    if [ "$OS" == "linux" ]; then
        echo "Run: sudo apt install python3 python3-pip"
    elif [ "$OS" == "windows" ]; then
        echo "Download from: https://python.org/downloads"
    fi
    exit 1
fi

PYTHON_VER=$(python3 --version)
echo -e "${GREEN}$PYTHON_VER${NC}"

# Install Python dependencies
echo "Installing Python packages..."
pip3 install --quiet --break-system-packages websockets psutil pyyaml 2>/dev/null || \
pip3 install --quiet websockets psutil pyyaml 2>/dev/null || \
pip3 install --user websockets psutil pyyaml

# Install optional: screen capture
echo "Installing screen capture packages..."
pip3 install --quiet --break-system-packages mss Pillow 2>/dev/null || \
pip3 install --quiet mss Pillow 2>/dev/null || \
pip3 install --user mss Pillow || \
echo -e "${YELLOW}Warning: Could not install mss/Pillow. Remote desktop won't work.${NC}"

# Linux: install xdotool for remote desktop input
if [ "$OS" == "linux" ]; then
    if ! command -v xdotool &> /dev/null; then
        echo "Installing xdotool (for remote desktop input)..."
        sudo apt-get install -y -qq xdotool 2>/dev/null || \
        echo -e "${YELLOW}Warning: Could not install xdotool. Remote desktop input won't work.${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}── Creating Config ──${NC}"
echo ""

# Create config.yaml
cat > "$AGENT_DIR/config.yaml" << EOF
relay_url: "$RELAY_URL"
agent_token: "$AGENT_TOKEN"
heartbeat_interval: 15
reconnect_base_delay: 1
reconnect_max_delay: 60
shell_default_cols: 120
shell_default_rows: 30
allowed_paths: []
max_chunk_size: 524288
sysinfo_cache_seconds: 2
EOF

echo -e "${GREEN}Config saved to agent/config.yaml${NC}"

# Make start.sh executable
chmod +x "$SCRIPT_DIR/start.sh" 2>/dev/null

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Setup Complete!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "Start the agent with: ${BLUE}./start.sh${NC}"
echo ""
