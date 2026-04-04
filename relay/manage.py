"""
CLI tool for managing RemoteController users.

Usage:
    python manage.py change-password <username> <new_password>
    python manage.py reset-2fa <username>
    python manage.py list-users
"""
import sys
from users import _load, force_change_password, disable_totp


def cmd_change_password(args):
    if len(args) < 2:
        print("Usage: python manage.py change-password <username> <new_password>")
        return
    result = force_change_password(args[0], args[1])
    print(f"[{'OK' if result['ok'] else 'ERROR'}] {result.get('error', 'Password changed')}")


def cmd_reset_2fa(args):
    if len(args) < 1:
        print("Usage: python manage.py reset-2fa <username>")
        return
    username = args[0].strip().lower()
    import json, threading
    from users import _lock, _load, _save
    with _lock:
        users = _load()
        user = users.get(username)
        if not user:
            print(f"[ERROR] User '{username}' not found")
            return
        user["totp_enabled"] = False
        user["totp_secret"] = None
        _save(users)
    print(f"[OK] 2FA disabled for '{username}'")


def cmd_list_users(args):
    users = _load()
    if not users:
        print("No users found.")
        return
    for name, data in users.items():
        tfa = "2FA ON" if data.get("totp_enabled") else "2FA OFF"
        print(f"  {name} [{tfa}]")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    commands = {
        "change-password": cmd_change_password,
        "reset-2fa": cmd_reset_2fa,
        "list-users": cmd_list_users,
    }

    cmd = sys.argv[1]
    fn = commands.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return
    fn(sys.argv[2:])


if __name__ == "__main__":
    main()
