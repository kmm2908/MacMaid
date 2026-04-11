import os
from dataclasses import dataclass, field
from send2trash import send2trash


@dataclass
class CleanResult:
    moved: int = 0
    errors: int = 0
    bytes_freed: int = 0
    error_paths: list = field(default_factory=list)


def clean_items(items: list[dict], permanent: bool = False) -> CleanResult:
    result = CleanResult()
    for item in items:
        path = item["path"]
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Not found: {path}")
            if permanent:
                if os.path.isdir(path):
                    import shutil
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            else:
                send2trash(path)
            result.moved += 1
            result.bytes_freed += item.get("size_bytes", 0)
        except Exception as e:
            result.errors += 1
            result.error_paths.append((path, str(e)))
    return result
