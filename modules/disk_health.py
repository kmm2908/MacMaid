import subprocess
import re
from modules.base import make_result, make_item


def _run_diskutil() -> str:
    try:
        return subprocess.check_output(["diskutil", "info", "/"], text=True, timeout=10)
    except Exception:
        return ""


def _run_smart() -> str | None:
    try:
        out = subprocess.check_output(["smartctl", "-H", "/dev/disk0"], text=True, timeout=10)
        if "PASSED" in out:
            return "Verified"
        return "Warning"
    except FileNotFoundError:
        return None
    except Exception:
        return "Unknown"


def scan() -> dict:
    raw = _run_diskutil()
    items = []

    total_match = re.search(r"Total Size:\s+(.+?)\s+\(", raw)
    free_match = re.search(r"Volume Free Space:\s+(.+?)\s+\(", raw)

    if total_match:
        items.append(make_item("/", 0, f"Total: {total_match.group(1)}"))
    if free_match:
        items.append(make_item("/", 0, f"Free: {free_match.group(1)}"))

    smart = _run_smart()
    if smart:
        items.append(make_item("/dev/disk0", 0, f"SMART Status: {smart}"))
    else:
        items.append(make_item("/dev/disk0", 0, "SMART: smartctl not installed (brew install smartmontools)"))

    return make_result(
        "Disk Health",
        "inform-only",
        action="none",
        suggestion="Disk health overview",
        items=items,
    )
