import os
from modules.base import make_result, make_item

TRASH_PATH = os.path.expanduser("~/.Trash")


def _trash_size() -> int:
    total = 0
    for dirpath, _, filenames in os.walk(TRASH_PATH):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def scan() -> dict:
    size = _trash_size()
    if size == 0:
        return make_result("Trash", "safe", action="empty-trash", suggestion="Trash is empty")
    size_mb = size / (1024 ** 2)
    items = [make_item(TRASH_PATH, size, f"Trash ({size_mb:.0f} MB)")]
    return make_result(
        "Trash",
        "safe",
        action="empty-trash",
        suggestion=f"Empty Trash to permanently free {size_mb:.0f} MB",
        items=items,
    )
