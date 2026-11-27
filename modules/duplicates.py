import os
import hashlib
from collections import defaultdict
from modules.base import make_result, make_item
import config as cfg


def _md5(path: str) -> str | None:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def scan() -> dict:
    scan_paths = [os.path.expanduser(p) for p in (cfg.get("scan_paths") or ["~/Downloads"])]
    hash_map: dict[str, list[dict]] = defaultdict(list)

    # One entry per real file: overlapping scan paths and hard links reach the same
    # inode twice, and listing it as a duplicate would offer up the only copy.
    seen: set[tuple[int, int]] = set()

    for base in scan_paths:
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    # A symlink is not a copy; trashing its target would lose the data.
                    if os.path.islink(fp):
                        continue
                    stat = os.stat(fp)
                    inode = (stat.st_dev, stat.st_ino)
                    if stat.st_size == 0 or inode in seen:
                        continue
                    digest = _md5(fp)
                    if digest:
                        seen.add(inode)
                        hash_map[digest].append({
                            "path": fp,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "label": f,
                            "linked": stat.st_nlink > 1,
                        })
                except OSError:
                    pass

    items = []
    for digest, files in hash_map.items():
        if len(files) < 2:
            continue
        # Keep a hard-linked file if there is one, else the newest; flag the rest.
        # Trashing one name of a hard-linked file frees nothing, so none is offered.
        files.sort(key=lambda x: (x["linked"], x["mtime"]), reverse=True)
        for dup in (f for f in files[1:] if not f["linked"]):
            items.append(make_item(
                dup["path"], dup["size"], dup["label"],
                meta={"duplicate_of": files[0]["path"]}
            ))

    total = sum(i["size_bytes"] for i in items)
    size_mb = total / (1024 ** 2)
    return make_result(
        "Duplicates",
        "review",
        action="trash",
        suggestion=f"{len(items)} duplicate files found ({size_mb:.0f} MB) — one copy of each kept",
        items=items,
    )
