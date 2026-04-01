# RemoteController

Control your PC remotely from your phone browser. Works behind NAT without port forwarding.

```
Phone (Browser) <--WSS--> VPS (Relay Server) <--WSS--> PC (Agent)
```

## Features

- **Terminal** - Full interactive bash shell (colors, vim, htop, tab completion)
- **File Manager** - Browse, download, upload files
- **System Monitor** - CPU, RAM, disk, network, GPU (NVIDIA) stats
- **Remote Desktop** - Screen viewing with mouse/keyboard control (desktop browsers only)
- **Mobile Optimized** - Virtual keyboard helper bar, responsive UI
- **Secure** - Argon2 password hashing, JWT tokens, rate limiting

## Requirements

**Relay Server (VPS):**
- Python 3.10+
- Any cheap VPS ($3-5/month) or free tier (Oracle Cloud)

**PC Agent:**
- Python 3.10+
- Linux (PTY shell requires Linux)
- `xdotool` for remote desktop input (optional)
- `nvidia-smi` for GPU monitoring (optional)

## Quick Setup

### 1. Generate Tokens

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Run this twice - one for `secret_key`, one for `agent_token`.

### 2. Relay Server (on VPS)

```bash
git clone https://github.com/YOUR_USERNAME/RemoteController.git
cd RemoteController

# Create config from example
cp relay/config.example.yaml relay/config.yaml

# Edit config - set your generated tokens
nano relay/config.yaml

# Install dependencies
cd relay
python3 -m venv ../venv
source ../venv/bin/activate
pip install -r requirements.txt

# Run
python main.py
```

### 3. PC Agent (on your PC)

```bash
# Create config from example
cp agent/config.example.yaml agent/config.yaml

# Edit config - set your VPS IP and matching agent_token
nano agent/config.yaml

# Install dependencies
pip install -r agent/requirements.txt

# Optional: for remote desktop
pip install mss Pillow
sudo apt install xdotool  # for mouse/keyboard control

# Run
cd agent
python3 main.py
```

### 4. Access

Open `http://YOUR_VPS_IP:3131` in your phone browser. First login sets the password.

## Run as Service

### Relay (systemd)

```bash
sudo cat > /etc/systemd/system/remotecontroller.service << 'EOF'
[Unit]
Description=RemoteController Relay Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/remotecontroller/relay
ExecStart=/opt/remotecontroller/venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now remotecontroller
```

### Agent (systemd)

```bash
sudo cat > /etc/systemd/system/rc-agent.service << 'EOF'
[Unit]
Description=RemoteController PC Agent
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/RemoteController/agent
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now rc-agent
```

## Nginx Reverse Proxy (Optional)

For domain + HTTPS:

```nginx
server {
    listen 80;
    server_name your.domain.com;

    location / {
        proxy_pass http://127.0.0.1:3131;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
}
```

Then: `sudo certbot --nginx -d your.domain.com`

## Security

- **Password**: Hashed with Argon2 (GPU brute-force resistant)
- **Sessions**: JWT tokens (24h expiry, HS256 signed)
- **Rate limiting**: 5 failed logins per minute per IP
- **Agent auth**: Pre-shared token with timing-safe comparison
- **Session storage**: Token cleared when browser closes
- **File access**: Optional path restriction via `allowed_paths`

## Architecture

```
relay/              # Runs on VPS
├── main.py         # FastAPI server
├── auth.py         # JWT + Argon2 auth
├── connection_manager.py  # WebSocket routing
├── routes_ws.py    # /ws/agent, /ws/client endpoints
├── routes_api.py   # /api/login, /api/health
└── config.py       # Config loader

agent/              # Runs on your PC
├── main.py         # Message dispatcher
├── ws_client.py    # Auto-reconnecting WS client
├── shell.py        # PTY interactive shell
├── file_ops.py     # File browser operations
├── sysinfo.py      # System + GPU monitoring
├── screen.py       # Screen capture + input
└── config.py       # Config loader

web/                # Served by relay, runs in browser
├── index.html      # Login page
├── app.html        # Main app (Terminal, Files, System, Screen)
├── css/style.css   # Dark theme, mobile responsive
└── js/             # Auth, WebSocket, Terminal, Files, Dashboard, Screen
```

## License

MIT
