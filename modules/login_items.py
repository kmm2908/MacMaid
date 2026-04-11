import subprocess
import os
from modules.base import make_result, make_item

OSASCRIPT = """
tell application "System Events"
    set loginItems to every login item
    set output to ""
    repeat with li in loginItems
        set output to output & (name of li) & ", " & (path of li) & ", " & (exists of li) & "\n"
    end repeat
    return output
end tell
"""


def _run_osascript() -> str:
    try:
        return subprocess.check_output(["osascript", "-e", OSASCRIPT], text=True, timeout=15)
    except Exception:
        return ""


def scan() -> dict:
    raw = _run_osascript()
    items = []

    for line in raw.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name, path, exists_str = parts[0], parts[1], parts[2]
        path_exists = exists_str.lower() == "true" and os.path.exists(path)
        items.append(make_item(
            path, 0, name,
            meta={"path_exists": path_exists, "path": path}
        ))

    dead_count = sum(1 for i in items if not i["meta"]["path_exists"])
    suggestion = f"{len(items)} login items found"
    if dead_count:
        suggestion += f" — {dead_count} have missing paths (dead entries)"

    return make_result(
        "Login Items",
        "inform-only",
        action="none",
        suggestion=suggestion,
        items=items,
    )
