"""Auto-clean ~/Downloads: files untouched for a day go to Trash unless red-tagged.

Ported from the standalone CleanUp project. Off unless switched on in config.
"""
import binascii
import os
import plistlib
import subprocess
import time
from typing import Any

from modules.base import make_item, make_result

DOWNLOADS = os.path.expanduser("~/Downloads")
MIN_AGE_SECONDS = 86400
TAG_ATTR = "com.apple.metadata:_kMDItemUserTags"


def is_red_tagged(path: str) -> bool:
    """True if path has a red Finder tag, or if its tags cannot be read."""
    try:
        result = subprocess.run(["xattr", "-p", "-x", TAG_ATTR, path],
                                check=False, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return "No such xattr" not in result.stderr
        tags = plistlib.loads(binascii.unhexlify("".join(result.stdout.split())))
        return any(t.strip().lower() == "red" or t.endswith("\n6") for t in tags)
    except Exception:
        return True


def is_protected(path: str, root: str) -> bool:
    """True if path, any folder between it and root, or root itself is red-tagged."""
    while path != os.path.dirname(path):
        if is_red_tagged(path):
            return True
        if path == root:
            return False
        path = os.path.dirname(path)
    return False


def _only_leftovers(folder: str, going: set[str]) -> bool:
    try:
        return all(name == ".DS_Store" or os.path.join(folder, name) in going
                   for name in os.listdir(folder))
    except OSError:
        return False


def scan() -> dict[str, Any]:
    cutoff = time.time() - MIN_AGE_SECONDS
    items: list[dict[str, Any]] = []
    visited: list[str] = []
    unreadable: list[OSError] = []
    tagged = recent = 0

    if os.path.isdir(DOWNLOADS) and is_red_tagged(DOWNLOADS):
        return make_result("Downloads", "safe", action="trash",
                           suggestion="Kept everything: the Downloads folder itself is red-tagged")

    for current, dirnames, filenames in os.walk(DOWNLOADS, onerror=unreadable.append):
        visited.append(current)
        walk_into = []
        for name in dirnames:
            path = os.path.join(current, name)
            if os.path.islink(path):
                continue
            if is_red_tagged(path):
                tagged += 1
            else:
                walk_into.append(name)
        dirnames[:] = walk_into

        for name in filenames:
            path = os.path.join(current, name)
            if os.path.islink(path):
                continue
            try:
                info = os.stat(path)
            except FileNotFoundError:
                continue
            except OSError as e:
                unreadable.append(e)
                continue
            if is_red_tagged(path):
                tagged += 1
            elif info.st_mtime > cutoff:
                recent += 1
            else:
                items.append(make_item(
                    path, info.st_size, os.path.relpath(path, DOWNLOADS),
                    {"mtime": info.st_mtime, "red_tag_root": DOWNLOADS},
                ))

    files = len(items)
    going = {i["path"] for i in items}
    # Deepest first, so a parent is judged after the folders inside it
    for folder in reversed(visited[1:]):
        if _only_leftovers(folder, going):
            going.add(folder)
            items.append(make_item(
                folder, 0, os.path.relpath(folder, DOWNLOADS) + os.sep,
                {"only_if_empty": True, "red_tag_root": DOWNLOADS},
            ))

    suggestion = (f"{files} file(s) to Trash and {len(items) - files} emptied folder(s) removed; "
                  f"kept {tagged} red-tagged, {recent} recent (under 24h)")
    if unreadable:
        suggestion += (f". Could not read {len(unreadable)} item(s) — "
                       f"check macOS file access for this Python")
    return make_result("Downloads", "safe", action="trash",
                       suggestion=suggestion, items=items)
