"""Hourly low-storage check: alert before macOS starts force-quitting apps to free space."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import config as cfg
import emailer

GB = 1_000_000_000
STATE_PATH = Path.home() / "Library" / "Logs" / "mac-maid-storage-state.json"
DU_TIMEOUT_SECONDS = 120
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


def _dir_bytes(path: Path) -> int | None:
    """None when du could not read everything: a partial total would understate it."""
    try:
        done = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True,
                              timeout=DU_TIMEOUT_SECONDS, check=False)
        return int(done.stdout.split()[0]) * 1024 if done.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError):
        return None


def top_users() -> list[tuple[str, int | None]]:
    sized = [(name, _dir_bytes(path)) for name, path in SPACE_USERS if path.exists()]
    trash = [u for u in sized if u[0] == "Trash"]
    rest = sorted((u for u in sized if u[0] != "Trash"), key=lambda u: u[1] or -1, reverse=True)
    return trash + rest


def notify(title: str, message: str) -> None:
    script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10, check=False)
    except (subprocess.TimeoutExpired, OSError):
        pass  # the email still goes; a missing banner must not stop it


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


def _setting(key: str) -> float:
    """A config value, or its default when it is not a positive number."""
    value = cfg.get(key)
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    return float(value) if ok else float(cfg.DEFAULTS[key])


def _gb(n: float) -> str:
    return f"{n / GB:.1f} GB"


def _alert(current: str, free: int) -> bool:
    todo = "Empty the Trash if nothing in it is still needed, then look through the largest folder listed"
    notify("MacMaid — disk nearly full", f"{_gb(free)} free. Details are in your email.")
    users = top_users()
    subject = f"MacMaid: only {_gb(free)} free on the main disk"
    lines = [f"Free space on the main disk: {_gb(free)}.", "",
             "Sizes of selected common folders (Trash first: it holds files you have already deleted once):"]
    lines += [f"  {name}: {_gb(size) if size is not None else 'could not be measured'}"
              for name, size in users]
    lines += ["", "Below about 10 GB macOS starts force-quitting apps to reclaim space."]
    kind = {"urgent": todo} if current == "urgent" else {"action": todo}
    return emailer.send_report(subject, "\n".join(lines), cfg.get("email_report_to") or "", **kind)


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
