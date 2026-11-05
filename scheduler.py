import os
import sys
import subprocess
from pathlib import Path

import url_handler

PLIST_PATH = os.path.expanduser("~/Library/LaunchAgents/com.macmaid.nightly.plist")
SCRIPT_PATH = str(Path(__file__).parent / "main.py")
STORAGE_PLIST_PATH = os.path.expanduser("~/Library/LaunchAgents/com.macmaid.storage.plist")
STORAGE_INTERVAL_SECONDS = 3600


def _resolve_python() -> str:
    """Return the Python executable to embed in the LaunchAgent plist.

    Prefers the active venv interpreter so the LaunchAgent has access to
    installed packages. Falls back to the current interpreter if no venv
    is found.
    """
    if sys.prefix != sys.base_prefix:
        # Already running inside a venv — use it
        return sys.executable

    # Look for a venv next to this file
    project_dir = Path(__file__).parent
    for name in (".venv", "venv"):
        candidate = project_dir / name / "bin" / "python3"
        if candidate.exists():
            return str(candidate)

    return sys.executable


def build_plist(time_str: str) -> str:
    hour, minute = (int(x) for x in time_str.split(":"))
    python = _resolve_python()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.macmaid.nightly</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{SCRIPT_PATH}</string>
        <string>--unattended</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{os.path.expanduser("~/Library/Logs/mac-maid.log")}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.expanduser("~/Library/Logs/mac-maid-error.log")}</string>
</dict>
</plist>"""


def build_storage_plist() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.macmaid.storage</string>
    <key>ProgramArguments</key>
    <array>
        <string>{_resolve_python()}</string>
        <string>{SCRIPT_PATH}</string>
        <string>--storage-check</string>
    </array>
    <key>StartInterval</key>
    <integer>{STORAGE_INTERVAL_SECONDS}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{os.path.expanduser("~/Library/Logs/mac-maid-storage.log")}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.expanduser("~/Library/Logs/mac-maid-storage.log")}</string>
</dict>
</plist>"""


def _load_fresh(path: str, plist: str) -> None:
    # `launchctl load` errors when the label is already loaded, so unload first.
    subprocess.run(["launchctl", "unload", path], capture_output=True, check=False)
    with open(path, "w") as f:
        f.write(plist)
    subprocess.run(["launchctl", "load", path], check=True, capture_output=True)


def install(time_str: str) -> bool:
    try:
        _load_fresh(PLIST_PATH, build_plist(time_str))
        _load_fresh(STORAGE_PLIST_PATH, build_storage_plist())
        url_handler.setup(_resolve_python(), SCRIPT_PATH)
        return True
    except Exception:
        return False


def uninstall() -> bool:
    found = False
    for path in (PLIST_PATH, STORAGE_PLIST_PATH):
        if not os.path.exists(path):
            continue
        try:
            subprocess.run(["launchctl", "unload", path], capture_output=True, check=False)
            os.remove(path)
        except OSError:
            return False
        found = True
    return found


def _storage_loaded() -> bool:
    done = subprocess.run(["launchctl", "list", "com.macmaid.storage"], capture_output=True, check=False)
    return done.returncode == 0


def status() -> str:
    if os.path.exists(PLIST_PATH):
        storage = "hourly storage check on" if _storage_loaded() else "storage check not loaded"
        return f"Scheduled — plist at {PLIST_PATH} ({storage})"
    return "Not scheduled"
