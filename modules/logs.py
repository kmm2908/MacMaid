import os
import time
from modules.base import make_result, make_item
import config as cfg

USER_LOG_DIR = os.path.expanduser("~/Library/Logs")
SYS_LOG_DIR = "/private/var/log"


def _find_old_logs(base: str, cutoff: float) -> list[dict]:
    items = []
    if not os.path.isdir(base):
        return items
    for dirpath, _, filenames in os.walk(base):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                stat = os.stat(fp)
                if stat.st_mtime < cutoff:
                    items.append(make_item(fp, stat.st_size, f))
            except OSError:
                pass
    return items


def scan() -> dict:
    retention_days = cfg.get("log_retention_days") or 7
    cutoff = time.time() - (retention_days * 86400)
    items = _find_old_logs(USER_LOG_DIR, cutoff) + _find_old_logs(SYS_LOG_DIR, cutoff)
    total = sum(i["size_bytes"] for i in items)
    size_mb = total / (1024 ** 2)
    return make_result(
        "Logs",
        "safe",
        action="trash",
        suggestion=f"Remove {len(items)} log files older than {retention_days} days ({size_mb:.0f} MB)",
        items=items,
    )
