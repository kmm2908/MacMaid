import subprocess
import re
from modules.base import make_result, make_item

PAGE_SIZE = 16384  # bytes, M-series default


def _run_vm_stat() -> str:
    try:
        return subprocess.check_output(["vm_stat"], text=True, timeout=5)
    except Exception:
        return ""


def _pages_to_mb(pages: int) -> float:
    return (pages * PAGE_SIZE) / (1024 ** 2)


def scan() -> dict:
    raw = _run_vm_stat()
    items = []

    patterns = {
        "free": r"Pages free:\s+([\d]+)",
        "active": r"Pages active:\s+([\d]+)",
        "inactive": r"Pages inactive:\s+([\d]+)",
        "wired": r"Pages wired down:\s+([\d]+)",
        "compressed": r"Pages compressor:\s+([\d]+)",
    }

    values = {}
    for key, pattern in patterns.items():
        m = re.search(pattern, raw)
        if m:
            values[key] = int(m.group(1).rstrip("."))

    for key, pages in values.items():
        mb = _pages_to_mb(pages)
        items.append(make_item("memory", int(mb * 1024 * 1024), f"{key.title()}: {mb:.0f} MB"))

    total_used = sum(values.get(k, 0) for k in ["active", "wired", "compressed"])
    total_free = values.get("free", 0)
    total = total_used + total_free
    pressure = "Normal"
    if total > 0:
        used_pct = total_used / total
        if used_pct > 0.9:
            pressure = "Critical"
        elif used_pct > 0.75:
            pressure = "Warning"

    items.insert(0, make_item("memory", 0, f"Pressure: {pressure}"))

    return make_result(
        "Memory",
        "inform-only",
        action="none",
        suggestion=f"Memory pressure: {pressure}",
        items=items,
    )
