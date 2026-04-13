import os
import plistlib
from datetime import datetime
from modules.base import make_result, make_item

BACKUP_DIR = os.path.expanduser("~/Library/Application Support/MobileSync/Backup")


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _read_info(backup_path: str) -> dict:
    info_path = os.path.join(backup_path, "Info.plist")
    try:
        with open(info_path, "rb") as f:
            return plistlib.load(f)
    except Exception:
        return {}


def scan() -> dict:
    if not os.path.isdir(BACKUP_DIR):
        return make_result(
            "iOS Backups", "inform-only", action="none",
            suggestion="No iOS backups found (~/Library/Application Support/MobileSync/Backup)"
        )

    items = []
    try:
        entries = os.listdir(BACKUP_DIR)
    except OSError:
        entries = []

    for name in entries:
        full = os.path.join(BACKUP_DIR, name)
        if not os.path.isdir(full):
            continue
        size = _dir_size(full)
        info = _read_info(full)
        device = info.get("Display Name") or info.get("Device Name") or name[:8]
        last_backup = info.get("Last Backup Date")
        if isinstance(last_backup, datetime):
            date_str = last_backup.strftime("%Y-%m-%d")
        else:
            try:
                mtime = os.path.getmtime(full)
                date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            except OSError:
                date_str = "unknown"
        label = f"{device} — last backup {date_str}"
        items.append(make_item(full, size, label, meta={"last_backup": date_str, "device": device}))

    items.sort(key=lambda x: x["meta"].get("last_backup", ""), reverse=True)
    total = sum(i["size_bytes"] for i in items)
    size_gb = total / (1024 ** 3)

    return make_result(
        "iOS Backups",
        "review",
        action="trash",
        suggestion=f"{len(items)} backup(s) found ({size_gb:.1f} GB) — remove old devices or duplicates only",
        items=items,
    )
