import os
import sys
import subprocess
from pathlib import Path

PLIST_PATH = os.path.expanduser("~/Library/LaunchAgents/com.macmaid.nightly.plist")
SCRIPT_PATH = str(Path(__file__).parent / "main.py")


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


def install(time_str: str) -> bool:
    try:
        plist = build_plist(time_str)
        with open(PLIST_PATH, "w") as f:
            f.write(plist)
        subprocess.run(["launchctl", "load", PLIST_PATH], check=True, capture_output=True)
        return True
    except Exception:
        return False


def uninstall() -> bool:
    if not os.path.exists(PLIST_PATH):
        return False
    try:
        subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)
        os.remove(PLIST_PATH)
        return True
    except Exception:
        return False


def status() -> str:
    if os.path.exists(PLIST_PATH):
        return f"Scheduled — plist at {PLIST_PATH}"
    return "Not scheduled"
