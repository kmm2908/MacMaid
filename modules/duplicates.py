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

    for base in scan_paths:
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    stat = os.stat(fp)
                    if stat.st_size == 0:
                        continue
                    digest = _md5(fp)
                    if digest:
                        hash_map[digest].append({
                            "path": fp,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "label": f,
                        })
                except OSError:
                    pass

    items = []
    for digest, files in hash_map.items():
        if len(files) < 2:
            continue
        # Sort by mtime descending — keep newest, flag the rest
        files.sort(key=lambda x: x["mtime"], reverse=True)
        for dup in files[1:]:
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
        suggestion=f"{len(items)} duplicate files found ({size_mb:.0f} MB) — newest copy kept",
        items=items,
    )
