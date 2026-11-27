import os
import stat
import time

from modules.base import binned_before, binned_time_unknown, make_result, make_item
import config as cfg

TRASH_PATH = os.path.expanduser("~/.Trash")
VOLUMES_DIR = "/Volumes"
DEFAULT_RETENTION_DAYS = 7


def trash_dirs(unchecked: list[str] | None = None) -> list[str]:
    """Every trash folder this user owns: ~/.Trash plus each mounted volume's.

    External volumes keep their own /Volumes/<name>/.Trashes/<uid>, which is
    never emptied by anything that only looks at ~/.Trash.
    VOLUMES_DIR is added to `unchecked` if the volumes cannot be listed.
    """
    dirs = [TRASH_PATH]
    try:
        volumes = os.listdir(VOLUMES_DIR)
    except OSError:
        if unchecked is not None:
            unchecked.append(VOLUMES_DIR)
        return dirs
    for name in volumes:
        candidate = os.path.join(VOLUMES_DIR, name, ".Trashes", str(os.getuid()))
        try:
            if stat.S_ISDIR(os.stat(candidate).st_mode):
                dirs.append(candidate)
        except (FileNotFoundError, NotADirectoryError):
            pass
        except OSError:
            dirs.append(candidate)  # may exist: listing it will report it
    return dirs


def _folder_size(path: str) -> tuple[int, bool]:
    """(bytes that could be measured, whether that was everything)."""
    total = 0
    failures: list[OSError] = []
    for dirpath, _, filenames in os.walk(path, onerror=failures.append):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError as error:
                failures.append(error)
    # something that has gone since it was listed has no size to miss
    return total, all(isinstance(e, FileNotFoundError) for e in failures)


def reclaimable_size(trash_dir: str, older_than_days: int = DEFAULT_RETENTION_DAYS,
                     unchecked: list[str] | None = None) -> int:
    """Bytes held by entries binned long enough ago to be emptied — not the whole trash.

    Reporting the full size would promise space the retention window won't free.
    Anything whose age cannot be established is added to `unchecked`: an entry,
    or `trash_dir` itself if it cannot be listed.
    """
    unchecked = [] if unchecked is None else unchecked
    cutoff = time.time() - (older_than_days * 86400)
    total = 0
    try:
        names = os.listdir(trash_dir)
    except FileNotFoundError:
        return 0
    except OSError:
        unchecked.append(trash_dir)
        return 0
    for name in names:
        path = os.path.join(trash_dir, name)
        try:
            if not binned_before(path, cutoff):
                if binned_time_unknown(path):
                    unchecked.append(path)
                continue
            if os.path.isdir(path) and not os.path.islink(path):
                size, complete = _folder_size(path)
                total += size
                if not complete:
                    unchecked.append(path)
            else:
                total += os.path.getsize(path)
        except FileNotFoundError:
            pass  # gone since it was listed
        except OSError:
            unchecked.append(path)
    return total


def _label(trash_dir: str) -> str:
    return "Trash" if trash_dir == TRASH_PATH else f"Trash on {trash_dir.split(os.sep)[2]}"


def _unchecked_note(unchecked: list[str], dirs: list[str]) -> str:
    """What the scan could not check, or "" if it checked everything."""
    parts = [f"{_label(p)} (could not be opened)" for p in unchecked if p in dirs]
    if VOLUMES_DIR in unchecked:
        parts.append("Trash on other volumes (could not be listed)")
    entries = sum(p not in dirs and p != VOLUMES_DIR for p in unchecked)
    if entries:
        parts.append(f"{entries} item(s) with no reliable binned date or not fully readable")
    return f"could not check: {', '.join(parts)}" if parts else ""


def scan() -> dict:
    retention = cfg.get("trash_retention_days") or DEFAULT_RETENTION_DAYS
    items = []
    unchecked: list[str] = []
    dirs = trash_dirs(unchecked)
    for d in dirs:
        size = reclaimable_size(d, retention, unchecked)
        if size <= 0:
            continue
        items.append(make_item(d, size, f"{_label(d)} ({size / 1024**2:.0f} MB)"))

    note = _unchecked_note(unchecked, dirs)
    if not items:
        suggestion = (f"Found nothing to empty, but {note}" if note
                      else f"Nothing has been in the Trash longer than {retention} days")
        return make_result("Trash", "safe", action="empty-trash", suggestion=suggestion)
    total_mb = sum(i["size_bytes"] for i in items) / (1024 ** 2)
    suggestion = f"Permanently free {total_mb:.0f} MB of Trash binned more than {retention} days ago"
    if note:
        suggestion += f". {note[0].upper()}{note[1:]}"
    return make_result(
        "Trash",
        "safe",
        action="empty-trash",
        suggestion=suggestion,
        items=items,
    )
