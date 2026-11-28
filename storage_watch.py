"""Hourly low-storage check: alert before macOS starts force-quitting apps to free space."""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import config as cfg
import emailer
import fda_launcher

GB = 1_000_000_000
STATE_PATH = Path.home() / "Library" / "Logs" / "mac-maid-storage-state.json"
DU_TIMEOUT_SECONDS = 120
# Folders macOS refuses outright without Full Disk Access
PROTECTED_FOLDERS = {"Trash", "Mail", "iPhone backups"}
SEVERITY = {"ok": 0, "warn": 1, "urgent": 2}

HOME = Path.home()
# A fixed shortlist, not the whole disk. Trash comes first: it holds files already deleted once.
SPACE_USERS = [
    ("Trash", HOME / ".Trash"),
    ("Downloads", HOME / "Downloads"),
    ("Caches", HOME / "Library" / "Caches"),
    ("Xcode & simulators", HOME / "Library" / "Developer"),
    ("iPhone backups", HOME / "Library" / "Application Support" / "MobileSync" / "Backup"),
    ("Mail", HOME / "Library" / "Mail"),
    ("Desktop", HOME / "Desktop"),
    ("Documents", HOME / "Documents"),
]


def free_bytes() -> int:
    return shutil.disk_usage("/").free


def level(free: float, warn_gb: float, urgent_gb: float) -> str:
    if free < urgent_gb * GB:
        return "urgent"
    if free < warn_gb * GB:
        return "warn"
    return "ok"


def should_alert(current: str, state: dict, now: datetime, realert_hours: float) -> bool:
    if current == "ok":
        return False
    last = state.get("level", "ok")
    if SEVERITY[current] > SEVERITY.get(last, 0):
        return True
    try:
        alerted_at = datetime.fromisoformat(state["alerted_at"])
    except (KeyError, TypeError, ValueError):
        return True
    return now - alerted_at >= timedelta(hours=realert_hours)


class Measure(NamedTuple):
    bytes: int | None
    complete: bool = True
    blocked: bool = False
    timed_out: bool = False
    refused: bool = False  # the folder itself cannot be listed


def _refused(path: Path) -> bool:
    try:
        with os.scandir(path):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def _measure(path: Path) -> Measure:
    """du's total. When it could not read everything the total is only a minimum."""
    try:
        done = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True,
                              timeout=DU_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return Measure(None, complete=False, timed_out=True)
    except (OSError, ValueError):
        return Measure(None, complete=False)
    # macOS privacy protection (no Full Disk Access) reads differently from file permissions.
    blocked = "Operation not permitted" in done.stderr
    try:
        size = int(done.stdout.split()[0]) * 1024
    except (ValueError, IndexError):
        size = None
    return Measure(size, complete=done.returncode == 0 and size is not None, blocked=blocked,
                   refused=blocked and _refused(path))


def _size_text(measure: Measure) -> str:
    if measure.complete:
        return _gb(measure.bytes)
    # A minimum that would print as 0.0 GB says nothing about the folder.
    if measure.bytes is not None and measure.bytes >= GB / 10:
        return f"at least {_gb(measure.bytes)} (part of it could not be read)"
    if measure.timed_out:
        return "could not be measured (took too long)"
    if measure.blocked:
        return "could not be measured (macOS blocked access)"
    return "could not be measured"


def top_users() -> list[tuple[str, Measure]]:
    sized = [(name, _measure(path)) for name, path in SPACE_USERS if path.exists()]
    trash = [u for u in sized if u[0] == "Trash"]
    rest = sorted((u for u in sized if u[0] != "Trash"),
                  key=lambda u: -1 if u[1].bytes is None else u[1].bytes, reverse=True)
    return trash + rest


def local_snapshots() -> int | None:
    """How many local Time Machine snapshots the main disk holds; None if unknown."""
    try:
        done = subprocess.run(["tmutil", "listlocalsnapshots", "/"], capture_output=True, text=True,
                              timeout=30, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if done.returncode != 0:
        return None
    return sum(line.startswith("com.apple.TimeMachine.") for line in done.stdout.splitlines())


def _snapshot_lines() -> list[str]:
    count = local_snapshots()
    if count is None:
        return ["", "Local Time Machine snapshots: could not be checked."]
    if not count:
        return []
    return ["", f"There are {count} local Time Machine snapshot(s) on this disk. Deleting files may not free "
                "their space until those snapshots are thinned."]


def notify(title: str, message: str) -> bool:
    """Show a banner. False if macOS did not take it."""
    # AppleScript cannot read \uXXXX escapes, so non-ASCII text has to go in as it is.
    text, heading = (json.dumps(value, ensure_ascii=False) for value in (message, title))
    script = f"display notification {text} with title {heading}"
    # A missing banner must not stop the email; it is logged so it is not lost silently.
    try:
        done = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, errors="replace",
                              timeout=10, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"storage_watch: notification failed: {exc}")
        return False
    if done.returncode != 0:
        print(f"storage_watch: notification failed: {done.stderr.strip()}")
        return False
    return True


def _load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state))
    except OSError as exc:
        print(f"storage_watch: could not save state to {STATE_PATH}: {exc}")


def usable_setting(key: str, value: object) -> float:
    """value when it is a positive number, otherwise the setting's default."""
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    return value if ok else cfg.DEFAULTS[key]


def _setting(key: str) -> float:
    return float(usable_setting(key, cfg.get(key)))


def _access_lines() -> list[str]:
    if fda_launcher.EXECUTABLE.exists():
        return [f"To let it measure them, give Full Disk Access (System Settings > Privacy & Security) to "
                f"\"MacMaid Storage Check\" in {fda_launcher.APP_DIR.parent}. That app can only run this check."]
    return ["Giving Full Disk Access (System Settings > Privacy & Security) to the Python below would let it "
            "measure them, but every other script run by that Python could then read your Mail, Trash "
            "and backups too:", f"  {sys.executable}"]


def probe() -> None:
    """Print what this run can measure: proof, from launchd, that the access works."""
    for name, measure in top_users():
        print(f"{name}: {_size_text(measure)}")


def _gb(n: float) -> str:
    return f"{n / GB:.1f} GB"


def _alert(current: str, free: int) -> bool:
    to = cfg.get("email_report_to") or ""
    if not to:
        # A blank address means no email. The banner is then the whole alert.
        return notify("MacMaid — disk nearly full", f"{_gb(free)} free.")
    todo = "Empty the Trash if nothing in it is still needed, then look through the largest folder listed"
    notify("MacMaid — disk nearly full", f"{_gb(free)} free. Details are in your email.")
    users = top_users()
    subject = f"MacMaid: only {_gb(free)} free on the main disk"
    lines = [f"Free space on the main disk: {_gb(free)}.", "",
             "Sizes of selected common folders (Trash first: it holds files you have already deleted once):"]
    lines += [f"  {name}: {_size_text(measure)}" for name, measure in users]
    if any(name in PROTECTED_FOLDERS and measure.refused for name, measure in users):
        lines += ["", "macOS blocks this hourly check from some folders. You can leave it that way.", *_access_lines()]
    lines += _snapshot_lines()
    lines += ["", "Below about 10 GB macOS starts force-quitting apps to reclaim space."]
    kind = {"urgent": todo} if current == "urgent" else {"action": todo}
    return emailer.send_report(subject, "\n".join(lines), to, **kind)


def check(now: datetime | None = None) -> str:
    now = now or datetime.now()
    free = free_bytes()
    current = level(free, _setting("storage_warn_gb"), _setting("storage_urgent_gb"))
    state = _load_state()
    if current == "ok":
        _save_state({"level": "ok"})
        return current
    if should_alert(current, state, now, _setting("storage_realert_hours")) and _alert(current, free):
        _save_state({"level": current, "alerted_at": now.isoformat()})
    return current
