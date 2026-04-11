import os
from modules.base import make_result, make_item

USER_CACHE_DIR = os.path.expanduser("~/Library/Caches")
SYS_CACHE_DIR = "/Library/Caches"


def _dir_size(path: str) -> int:
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _scan_cache_dir(base: str) -> list[dict]:
    items = []
    if not os.path.isdir(base):
        return items
    try:
        for name in os.listdir(base):
            full = os.path.join(base, name)
            size = _dir_size(full) if os.path.isdir(full) else 0
            try:
                size = size or os.path.getsize(full)
            except OSError:
                continue
            if size > 0:
                items.append(make_item(full, size, name))
    except OSError:
        pass
    return items


def scan() -> dict:
    items = _scan_cache_dir(USER_CACHE_DIR) + _scan_cache_dir(SYS_CACHE_DIR)
    total = sum(i["size_bytes"] for i in items)
    size_gb = total / (1024 ** 3)
    return make_result(
        "Caches",
        "safe",
        action="trash",
        suggestion=f"Clear {size_gb:.1f} GB of app caches (safe to remove — apps rebuild them)",
        items=items,
    )
