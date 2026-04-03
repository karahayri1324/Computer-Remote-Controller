"""
Cross-platform auto-start installer for RemoteController Agent.

Usage:
    python install_service.py          # Install auto-start
    python install_service.py remove   # Remove auto-start
    python install_service.py status   # Check status

Windows: Creates Task Scheduler entry (runs at logon, hidden)
Linux:   Creates systemd user service (runs at login)
"""
import os
import sys
import subprocess
import shutil

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_NAME = "RemoteController"
IS_WINDOWS = sys.platform == "win32"


def find_python():
    """Find the best Python executable."""
    if IS_WINDOWS:
        # pythonw.exe for no console window
        for name in ["pythonw.exe", "pythonw", "python.exe", "python"]:
            path = shutil.which(name)
            if path:
                # Prefer pythonw
                if "pythonw" not in name:
                    pw = path.replace("python.exe", "pythonw.exe")
                    if os.path.exists(pw):
                        return pw
                return path
    else:
        for name in ["python3", "python"]:
            path = shutil.which(name)
            if path:
                return path
    return sys.executable


def install_requirements():
    """Install Python dependencies."""
    req_file = os.path.join(AGENT_DIR, "requirements.txt")
    if os.path.exists(req_file):
        print("Installing dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "-q"],
            check=True,
        )
        print("Dependencies installed.")


# ─── Windows ────────────────────────────────────────────────────────

def windows_install():
    python = find_python()
    script = os.path.join(AGENT_DIR, "run.pyw")

    # schtasks: create a task that runs at logon, no console window
    cmd = [
        "schtasks", "/Create",
        "/TN", SERVICE_NAME,
        "/TR", f'"{python}" "{script}"',
        "/SC", "ONLOGON",       # Trigger: user logon
        "/RL", "LIMITED",       # Normal privileges (not admin)
        "/F",                   # Force overwrite if exists
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] Task '{SERVICE_NAME}' created.")
        print(f"     Python: {python}")
        print(f"     Script: {script}")
        print(f"     Trigger: At user logon (hidden, no console)")
        print()
        print("The agent will start automatically when you log in.")
        print("To start it now, run: python run.pyw")
    else:
        print(f"[ERROR] Failed to create task: {result.stderr.strip()}")
        print("Try running as Administrator.")
        return False
    return True


def windows_remove():
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", SERVICE_NAME, "/F"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[OK] Task '{SERVICE_NAME}' removed.")
    else:
        print(f"[INFO] Task not found or already removed.")


def windows_status():
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", SERVICE_NAME, "/FO", "LIST"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[INSTALLED] Task '{SERVICE_NAME}' exists:")
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and ":" in line:
                print(f"  {line}")
    else:
        print(f"[NOT INSTALLED] Task '{SERVICE_NAME}' not found.")


# ─── Linux ──────────────────────────────────────────────────────────

def linux_service_path():
    d = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "remotecontroller.service")


def linux_install():
    python = find_python()
    main_py = os.path.join(AGENT_DIR, "main.py")
    service_path = linux_service_path()

    unit = f"""[Unit]
Description=RemoteController Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={AGENT_DIR}
ExecStart={python} {main_py}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    with open(service_path, "w") as f:
        f.write(unit)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "remotecontroller.service"], check=True)
    subprocess.run(["systemctl", "--user", "start", "remotecontroller.service"], check=True)

    # Enable lingering so service runs even when not logged in via GUI
    user = os.environ.get("USER", "")
    if user:
        subprocess.run(["loginctl", "enable-linger", user],
                       capture_output=True)

    print(f"[OK] Service installed and started.")
    print(f"     Python: {python}")
    print(f"     Unit: {service_path}")
    print()
    print("Commands:")
    print("  systemctl --user status remotecontroller")
    print("  systemctl --user stop remotecontroller")
    print("  systemctl --user restart remotecontroller")
    print("  journalctl --user -u remotecontroller -f")


def linux_remove():
    subprocess.run(["systemctl", "--user", "stop", "remotecontroller.service"],
                   capture_output=True)
    subprocess.run(["systemctl", "--user", "disable", "remotecontroller.service"],
                   capture_output=True)

    service_path = linux_service_path()
    if os.path.exists(service_path):
        os.remove(service_path)

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    print(f"[OK] Service removed.")


def linux_status():
    result = subprocess.run(
        ["systemctl", "--user", "is-active", "remotecontroller.service"],
        capture_output=True, text=True,
    )
    state = result.stdout.strip()
    service_path = linux_service_path()

    if os.path.exists(service_path):
        print(f"[INSTALLED] Service state: {state}")
        result2 = subprocess.run(
            ["systemctl", "--user", "status", "remotecontroller.service"],
            capture_output=True, text=True,
        )
        print(result2.stdout)
    else:
        print("[NOT INSTALLED] Service not found.")


# ─── Main ───────────────────────────────────────────────────────────

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "install"

    if action == "install":
        install_requirements()
        print()
        if IS_WINDOWS:
            windows_install()
        else:
            linux_install()

    elif action == "remove":
        if IS_WINDOWS:
            windows_remove()
        else:
            linux_remove()

    elif action == "status":
        if IS_WINDOWS:
            windows_status()
        else:
            linux_status()

    else:
        print(f"Usage: python {os.path.basename(__file__)} [install|remove|status]")


if __name__ == "__main__":
    main()
