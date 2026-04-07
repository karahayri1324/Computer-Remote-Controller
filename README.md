# RemoteController

Control your PC remotely from your phone browser. Works behind NAT without port forwarding.

```
Phone (Browser) ──HTTPS──▶ Relay Server ◀──WSS─── Your PC (Agent)
```

## Features

- **Terminal** - Full interactive shell (bash/powershell)
- **File Manager** - Browse, download, upload files
- **System Monitor** - CPU, RAM, disk, network, GPU stats
- **Remote Desktop** - Screen view + mouse/keyboard control (desktop only)
- **Mobile Optimized** - Touch-friendly UI with virtual keyboard helpers
- **Cross-Platform** - Works on Linux and Windows
- **Secure** - Argon2 hashing, JWT auth, HTTPS, rate limiting

## Setup (2 minutes)

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/RemoteController.git
cd RemoteController
```

### 2. Run Setup

**Linux / macOS:**
```bash
./setup.sh
```

**Windows (CMD or PowerShell):**
```cmd
setup.bat
```

It will ask you for:
- **Relay URL** - The server address (press Enter for default)
- **Username & Password** - Your account credentials

Setup automatically installs all dependencies.

### 3. Start

**Linux / macOS:**
```bash
./start.sh
```

**Windows:**
```cmd
start.bat
```

> **Tip:** On Windows you can also run `agent\start.bat` to start the agent in the background (no console window).

### 4. Open on Phone

Go to the relay server URL in your phone browser, enter your password, done.

## What You Need

- **Python 3.10+** on your PC
  - Windows: Download from [python.org](https://python.org/downloads) — check **"Add Python to PATH"** during install
  - Linux: `sudo apt install python3 python3-pip`

Optional (for remote desktop):
- Linux: `xdotool` (auto-installed by setup.sh)
- Windows: Nothing extra needed

## Architecture

```
relay/          # Relay server (managed by admin on VPS)
agent/          # Agent (runs on your PC)
web/            # Web UI (served by relay, opens on phone)
setup.sh        # One-time setup (Linux/macOS)
setup.bat       # One-time setup (Windows)
start.sh        # Start agent (Linux/macOS)
start.bat       # Start agent (Windows)
```

## Security

- Password hashed with **Argon2** (brute-force resistant)
- **JWT tokens** with 24h expiry
- **Rate limiting** - 5 failed logins per minute = blocked
- **HTTPS/WSS** encrypted transport
- Session cleared when browser closes
- Agent token verified with timing-safe comparison

Without the password, nobody can access your PC.

## License

MIT
