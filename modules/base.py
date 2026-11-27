import ctypes
import os
import stat
import struct
from typing import Literal

RiskLevel = Literal["safe", "review", "inform-only"]
ActionType = Literal["trash", "empty-trash", "none"]

# Alias for import compatibility
ModuleResult = dict

# macOS trash folder names: ~/.Trash on the boot volume, /Volumes/<x>/.Trashes elsewhere.
TRASH_DIR_NAMES = frozenset({".Trash", ".Trashes"})


def is_in_trash(path: str) -> bool:
    """True if path IS a trash folder or lives inside one.

    Scans must never descend into the trash: anything already there has been
    deleted once, and re-offering it inflates the freed-bytes count and makes
    the candidate list grow every night.
    """
    return any(part in TRASH_DIR_NAMES for part in os.path.normpath(path).split(os.sep))


class _AttrList(ctypes.Structure):
    _fields_ = [("bitmapcount", ctypes.c_ushort), ("reserved", ctypes.c_uint16),
                ("commonattr", ctypes.c_uint32), ("volattr", ctypes.c_uint32),
                ("dirattr", ctypes.c_uint32), ("fileattr", ctypes.c_uint32),
                ("forkattr", ctypes.c_uint32)]


# From <sys/attr.h>
_ATTR_BIT_MAP_COUNT = 5
_ATTR_CMN_RETURNED_ATTRS = 0x80000000
_ATTR_CMN_ADDEDTIME = 0x10000000
_FSOPT_NOFOLLOW = 0x1


def added_time(path: str) -> float | None:
    """When `path` was put into its current folder (Finder's "Date Added").

    None if the file system cannot say.
    """
    wanted = _AttrList(_ATTR_BIT_MAP_COUNT, 0,
                       _ATTR_CMN_RETURNED_ATTRS | _ATTR_CMN_ADDEDTIME, 0, 0, 0, 0)
    # u32 length, 5 x u32 attributes returned, then the timespec
    buf = ctypes.create_string_buffer(40)
    try:
        failed = ctypes.CDLL(None).getattrlist(
            os.fsencode(path), ctypes.byref(wanted), buf,
            ctypes.c_size_t(len(buf)), ctypes.c_ulong(_FSOPT_NOFOLLOW))
    except (OSError, AttributeError):
        return None
    if failed or not struct.unpack_from("=I", buf.raw, 4)[0] & _ATTR_CMN_ADDEDTIME:
        return None
    seconds, nanoseconds = struct.unpack_from("=qq", buf.raw, 24)
    return seconds + nanoseconds / 1e9 if seconds > 0 else None


def binned_before(path: str, cutoff: float) -> bool:
    """True only if a Trash entry is known to have been binned before `cutoff`.

    Moving to Trash keeps the old modification time, so that alone would empty an
    old file the night it was binned. A later write anywhere inside still keeps
    the entry, and an unknown binned time always does. So does a hard-linked file:
    Apple documents Date Added as inconsistent for those.

    Raises OSError if the entry cannot be fully read.
    """
    info = os.lstat(path)
    is_folder = stat.S_ISDIR(info.st_mode)
    if not is_folder and info.st_nlink > 1:
        return False
    added = added_time(path)
    if added is None or max(added, info.st_mtime) >= cutoff:
        return False
    # newest_mtime walks through a symlinked top folder, so only real folders
    return not is_folder or newest_mtime(path, strict=True) < cutoff


def binned_time_unknown(path: str) -> bool:
    """True if there is no trustworthy record of when this Trash entry was binned.

    Raises OSError if the entry cannot be read.
    """
    info = os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) and info.st_nlink > 1:
        return True
    return added_time(path) is None


def is_removable(path: str) -> bool:
    """True if this process could actually delete `path`.

    Removing an entry needs write+execute on its PARENT directory, not on the
    entry itself. Modules must not offer what the cleaner can never remove —
    root-owned paths like /private/var/log otherwise fail on every single run.
    """
    try:
        if os.stat(path).st_uid != os.getuid():
            return False
    except OSError:
        return False
    return os.access(os.path.dirname(path), os.W_OK | os.X_OK)


def _raise(error: OSError) -> None:
    raise error


def newest_mtime(path: str, strict: bool = False) -> float:
    """Latest modification time of a folder or anything inside it.

    `strict` raises OSError rather than skip anything that cannot be read.
    """
    newest = os.lstat(path).st_mtime
    for dirpath, dirnames, filenames in os.walk(path, onerror=_raise if strict else None):
        for name in dirnames + filenames:
            try:
                newest = max(newest, os.lstat(os.path.join(dirpath, name)).st_mtime)
            except OSError:
                if strict:
                    raise
    return newest


def make_item(path: str, size_bytes: int, label: str, meta: dict | None = None) -> dict:
    return {
        "path": path,
        "size_bytes": size_bytes,
        "label": label,
        "meta": meta or {},
    }


def make_result(
    category: str,
    risk: RiskLevel,
    action: ActionType = "trash",
    suggestion: str = "",
    items: list | None = None,
) -> dict:
    items = items or []
    return {
        "category": category,
        "risk": risk,
        "items": items,
        "total_size_bytes": sum(i["size_bytes"] for i in items),
        "suggestion": suggestion,
        "action": action,
    }
