import os
import time
from datetime import datetime
from modules.base import make_result, make_item
import config as cfg

SCAN_PATHS = [os.path.expanduser(p) for p in (cfg.get("scan_paths") or ["~/Downloads"])]
THRESHOLD_BYTES = (cfg.get("large_file_threshold_mb") or 500) * 1024 * 1024
OLD_FILE_SECONDS = (cfg.get("old_file_days") or 180) * 86400


def scan() -> dict:
    items = []
    now = time.time()
    for base in SCAN_PATHS:
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    stat = os.stat(fp)
                    age = now - stat.st_mtime
                    if stat.st_size >= THRESHOLD_BYTES or age >= OLD_FILE_SECONDS:
                        last_opened = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
                        items.append(make_item(
                            fp, stat.st_size, f,
                            meta={"last_modified": last_opened, "age_days": int(age // 86400)}
                        ))
                except OSError:
                    pass
    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    total = sum(i["size_bytes"] for i in items)
    size_gb = total / (1024 ** 3)
    return make_result(
        "Large & Old Files",
        "review",
        action="trash",
        suggestion=f"{len(items)} large or old files found ({size_gb:.1f} GB) — review before removing",
        items=items,
    )
