import os
from modules.base import make_result, make_item

MAIL_DIR = os.path.expanduser("~/Library/Mail")


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
    if not os.path.isdir(MAIL_DIR):
        return make_result("Mail Store", "review", action="trash",
                           suggestion="Mail.app directory not found")
    size = _dir_size(MAIL_DIR)
    size_mb = size / (1024 ** 2)
    items = [make_item(MAIL_DIR, size, f"Mail Store ({size_mb:.0f} MB)")] if size > 0 else []
    return make_result(
        "Mail Store",
        "review",
        action="trash",
        suggestion=f"Mail store is {size_mb:.0f} MB — only remove if you don't need offline access to email",
        items=items,
    )
