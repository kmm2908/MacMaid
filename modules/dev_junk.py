import os
from modules.base import make_result, make_item
import config as cfg

DEV_SCAN_PATHS = [os.path.expanduser(p) for p in (cfg.get("dev_scan_paths") or ["~/"])]
XCODE_DERIVED = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
PIP_CACHE = os.path.expanduser("~/Library/Caches/pip")
NPM_CACHE = os.path.expanduser("~/.npm/_cacache")

TARGET_DIRS = {"node_modules", "__pycache__", ".mypy_cache", ".pytest_cache"}
TARGET_EXTS = {".pyc"}


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _scan_path(base: str, items: list) -> None:
    if not os.path.isdir(base):
        return
    for dirpath, dirnames, filenames in os.walk(base, topdown=True):
        for d in list(dirnames):
            if d in TARGET_DIRS:
                full = os.path.join(dirpath, d)
                size = _dir_size(full)
                items.append(make_item(full, size, f"{d} ({os.path.basename(dirpath)})"))
                dirnames.remove(d)  # don't recurse into it
        for f in filenames:
            if os.path.splitext(f)[1] in TARGET_EXTS:
                fp = os.path.join(dirpath, f)
                try:
                    items.append(make_item(fp, os.path.getsize(fp), f))
                except OSError:
                    pass


def scan() -> dict:
    items = []
    for path in DEV_SCAN_PATHS:
        _scan_path(path, items)
    for static_path in [XCODE_DERIVED, PIP_CACHE, NPM_CACHE]:
        if os.path.isdir(static_path):
            size = _dir_size(static_path)
            if size > 0:
                items.append(make_item(static_path, size, os.path.basename(static_path)))
    total = sum(i["size_bytes"] for i in items)
    size_gb = total / (1024 ** 3)
    return make_result(
        "Dev Junk",
        "safe",
        action="trash",
        suggestion=f"Remove {len(items)} dev artefacts ({size_gb:.1f} GB)",
        items=items,
    )
