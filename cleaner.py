import os
import shutil
import time
from dataclasses import dataclass, field
from send2trash import send2trash

DEFAULT_TRASH_RETENTION_DAYS = 7


@dataclass
class CleanResult:
    moved: int = 0
    errors: int = 0
    bytes_freed: int = 0
    error_paths: list = field(default_factory=list)
    moved_paths: list = field(default_factory=list)
    skipped: int = 0


def plan_items(items: list[dict]) -> tuple[list[dict], int]:
    """Drop candidates whose removal is already implied by an earlier one.

    Two sources of guaranteed failure, both seen in production:
      - the same path listed by two modules (browsers + caches both claim
        ~/Library/Caches/com.apple.Safari)
      - a path nested under an earlier candidate — trashing the parent takes
        the child with it, so the child then raises FileNotFoundError

    Pure: returns a new list, never mutates the input.
    """
    kept: list[dict] = []
    seen: set[str] = set()
    removed_roots: list[str] = []
    dropped = 0
    for item in items:
        path = os.path.normpath(item["path"])
        if path in seen:
            dropped += 1
            continue
        if any(path.startswith(root + os.sep) for root in removed_roots):
            dropped += 1
            continue
        seen.add(path)
        # An emptied trash folder still exists afterwards, so it does not
        # imply the removal of anything nested beneath it.
        if item.get("action") != "empty-trash":
            removed_roots.append(path)
        kept.append(item)
    return kept, dropped


def _entry_size(path: str) -> int:
    if os.path.isfile(path) or os.path.islink(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def empty_trash(trash_dir: str, older_than_days: int = DEFAULT_TRASH_RETENTION_DAYS
                ) -> tuple[int, int, int]:
    """Permanently remove trash entries older than `older_than_days`.

    Deletes the CONTENTS, never the trash folder itself — macOS recreates it,
    but removing it breaks Finder's Trash until reboot. Entries newer than the
    retention window stay recoverable.

    Returns (removed, bytes_freed, errors).
    """
    removed = freed = errors = 0
    if not os.path.isdir(trash_dir):
        return (0, 0, 0)
    cutoff = time.time() - (older_than_days * 86400)
    try:
        names = os.listdir(trash_dir)
    except OSError:
        return (0, 0, 1)
    for name in names:
        path = os.path.join(trash_dir, name)
        try:
            if os.lstat(path).st_mtime >= cutoff:
                continue
            size = _entry_size(path)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed += 1
            freed += size
        except OSError:
            errors += 1
    return (removed, freed, errors)


def clean_items(items: list[dict], permanent: bool = False,
                trash_retention_days: int = DEFAULT_TRASH_RETENTION_DAYS) -> CleanResult:
    result = CleanResult()
    planned, dropped = plan_items(items)
    result.skipped = dropped
    for item in planned:
        path = item["path"]
        try:
            if item.get("action") == "empty-trash":
                removed, freed, errors = empty_trash(path, trash_retention_days)
                result.moved += removed
                result.bytes_freed += freed
                result.errors += errors
                if removed:
                    result.moved_paths.append(path)
                continue
            if not os.path.exists(path):
                raise FileNotFoundError(f"Not found: {path}")
            if permanent:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            else:
                send2trash(path)
            result.moved += 1
            result.bytes_freed += item.get("size_bytes", 0)
            result.moved_paths.append(path)
        except Exception as e:
            result.errors += 1
            result.error_paths.append((path, str(e)))
    return result
