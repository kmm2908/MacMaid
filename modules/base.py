import os
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
