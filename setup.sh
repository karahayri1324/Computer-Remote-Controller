#!/bin/bash
set -e

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
if [[ "$OSTYPE" == "linux-gnu"* ]]; then OS="linux"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then OS="windows"
elif [[ "$OSTYPE" == "darwin"* ]]; then OS="mac"
fi
echo -e "${GREEN}OS:${NC} $OS"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/agent"

echo ""
echo -e "${YELLOW}── Server ──${NC}"
echo ""
read -p "Relay server URL [https://rc.thinkerchat.com]: " SERVER_URL
SERVER_URL="${SERVER_URL:-https://rc.thinkerchat.com}"
# Remove trailing slash
SERVER_URL="${SERVER_URL%/}"

echo ""
echo -e "${YELLOW}── Account ──${NC}"
echo ""
read -p "Username (min 3 chars, alphanumeric): " USERNAME
read -s -p "Password (min 4 chars): " PASSWORD
echo ""

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
    echo -e "${RED}Error: Username and password cannot be empty.${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}── Registering Account ──${NC}"
echo ""

# Register via API
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"$USERNAME\", \"password\": \"$PASSWORD\"}" 2>&1)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "200" ]; then
    AGENT_TOKEN=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['agent_token'])" 2>/dev/null)
    if [ -z "$AGENT_TOKEN" ]; then
        echo -e "${RED}Error: Could not parse agent token from response.${NC}"
        echo "$BODY"
        exit 1
    fi
    echo -e "${GREEN}Account created successfully!${NC}"
elif [ "$HTTP_CODE" == "400" ]; then
    ERROR=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','Unknown error'))" 2>/dev/null || echo "$BODY")
    if echo "$ERROR" | grep -qi "already exists"; then
        echo -e "${YELLOW}Account already exists. Logging in to verify...${NC}"
        # Try login to verify credentials
        LOGIN_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/login" \
            -H "Content-Type: application/json" \
            -d "{\"username\": \"$USERNAME\", \"password\": \"$PASSWORD\"}" 2>&1)
        LOGIN_CODE=$(echo "$LOGIN_RESP" | tail -1)
        if [ "$LOGIN_CODE" != "200" ]; then
            echo -e "${RED}Error: Wrong password for existing account.${NC}"
            exit 1
        fi
        echo -e "${GREEN}Credentials verified!${NC}"
        echo -e "${YELLOW}Note: Using existing account. Agent token was shown only at registration.${NC}"
        echo -e "${YELLOW}If you lost your agent token, you need to create a new account.${NC}"
        read -p "Enter your agent token: " AGENT_TOKEN
        if [ -z "$AGENT_TOKEN" ]; then
            echo -e "${RED}Error: Agent token required.${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Error: $ERROR${NC}"
        exit 1
    fi
else
    echo -e "${RED}Error: Could not connect to server (HTTP $HTTP_CODE)${NC}"
    echo "$BODY"
    exit 1
fi

echo ""
echo -e "${YELLOW}── Installing Dependencies ──${NC}"
echo ""

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed!${NC}"
    if [ "$OS" == "linux" ]; then echo "Run: sudo apt install python3 python3-pip"
    elif [ "$OS" == "windows" ]; then echo "Download from: https://python.org/downloads"
    fi
    exit 1
fi

echo -e "${GREEN}$(python3 --version)${NC}"

echo "Installing Python packages..."
pip3 install --quiet --break-system-packages websockets psutil pyyaml 2>/dev/null || \
pip3 install --quiet websockets psutil pyyaml 2>/dev/null || \
pip3 install --user --quiet websockets psutil pyyaml

echo "Installing screen capture packages..."
pip3 install --quiet --break-system-packages mss Pillow 2>/dev/null || \
pip3 install --quiet mss Pillow 2>/dev/null || \
pip3 install --user --quiet mss Pillow || \
echo -e "${YELLOW}Warning: Could not install mss/Pillow. Remote desktop won't work.${NC}"

if [ "$OS" == "linux" ]; then
    if ! command -v xdotool &> /dev/null; then
        echo "Installing xdotool..."
        sudo apt-get install -y -qq xdotool 2>/dev/null || \
        echo -e "${YELLOW}Warning: Could not install xdotool.${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}── Creating Config ──${NC}"
echo ""

# Build WebSocket URL from server URL
WS_URL=$(echo "$SERVER_URL" | sed 's|^https://|wss://|; s|^http://|ws://|')
WS_URL="${WS_URL}/ws/agent"

cat > "$AGENT_DIR/config.yaml" << EOF
relay_url: "$WS_URL"
username: "$USERNAME"
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

echo -e "${GREEN}Config saved.${NC}"
chmod +x "$SCRIPT_DIR/start.sh" 2>/dev/null

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗"
echo -e "║         Setup Complete!              ║"
echo -e "╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Username: ${BLUE}$USERNAME${NC}"
echo -e "  Server:   ${BLUE}$SERVER_URL${NC}"
echo ""
echo -e "  Start:    ${BLUE}./start.sh${NC}"
echo -e "  Login:    Open ${BLUE}$SERVER_URL${NC} on your phone"
echo ""
echo -e "${YELLOW}IMPORTANT: Save your agent token! You'll need it if you reinstall.${NC}"
echo -e "  Token:    ${BLUE}$AGENT_TOKEN${NC}"
echo ""
