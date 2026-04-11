import os
from modules.base import make_result, make_item

BROWSER_CACHE_DIRS = {
    "Safari": os.path.expanduser("~/Library/Caches/com.apple.Safari"),
    "Chrome": os.path.expanduser("~/Library/Caches/Google/Chrome"),
    "Firefox": os.path.expanduser("~/Library/Caches/Firefox"),
}


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def scan() -> dict:
    items = []
    for browser, path in BROWSER_CACHE_DIRS.items():
        if os.path.isdir(path):
            size = _dir_size(path)
            if size > 0:
                items.append(make_item(path, size, f"{browser} Cache"))
    total = sum(i["size_bytes"] for i in items)
    size_mb = total / (1024 ** 2)
    return make_result(
        "Browser Caches",
        "safe",
        action="trash",
        suggestion=f"Clear {size_mb:.0f} MB of browser caches (browsers rebuild automatically)",
        items=items,
    )
