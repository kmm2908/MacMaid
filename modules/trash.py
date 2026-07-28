import os
import time

from modules.base import make_result, make_item
import config as cfg

TRASH_PATH = os.path.expanduser("~/.Trash")
VOLUMES_DIR = "/Volumes"
DEFAULT_RETENTION_DAYS = 7


def trash_dirs() -> list[str]:
    """Every trash folder this user owns: ~/.Trash plus each mounted volume's.

    External volumes keep their own /Volumes/<name>/.Trashes/<uid>, which is
    never emptied by anything that only looks at ~/.Trash.
    """
    dirs = [TRASH_PATH]
    try:
        volumes = os.listdir(VOLUMES_DIR)
    except OSError:
        return dirs
    for name in volumes:
        candidate = os.path.join(VOLUMES_DIR, name, ".Trashes", str(os.getuid()))
        if os.path.isdir(candidate):
            dirs.append(candidate)
    return dirs


def reclaimable_size(trash_dir: str, older_than_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Bytes held by entries old enough to be emptied — not the whole trash.

    Reporting the full size would promise space the retention window won't free.
    """
    cutoff = time.time() - (older_than_days * 86400)
    total = 0
    try:
        names = os.listdir(trash_dir)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(trash_dir, name)
        try:
            if os.lstat(path).st_mtime >= cutoff:
                continue
            if os.path.isdir(path) and not os.path.islink(path):
                for dirpath, _, filenames in os.walk(path):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except OSError:
                            pass
            else:
                total += os.path.getsize(path)
        except OSError:
            pass
    return total


def scan() -> dict:
    retention = cfg.get("trash_retention_days") or DEFAULT_RETENTION_DAYS
    items = []
    for d in trash_dirs():
        size = reclaimable_size(d, retention)
        if size <= 0:
            continue
        label = "Trash" if d == TRASH_PATH else f"Trash on {d.split(os.sep)[2]}"
        items.append(make_item(d, size, f"{label} ({size / 1024**2:.0f} MB)"))

    if not items:
        return make_result("Trash", "safe", action="empty-trash",
                           suggestion=f"Nothing in the Trash is older than {retention} days")
    total_mb = sum(i["size_bytes"] for i in items) / (1024 ** 2)
    return make_result(
        "Trash",
        "safe",
        action="empty-trash",
        suggestion=f"Permanently free {total_mb:.0f} MB of Trash older than {retention} days",
        items=items,
    )
