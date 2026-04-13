import json
import os
from datetime import datetime
from pathlib import Path

HISTORY_PATH = os.path.expanduser("~/Library/Logs/mac-maid-history.json")
MAX_ENTRIES = 90


def record(clean_result, dry_run: bool = False) -> None:
    """Append a run record to the history log."""
    entry = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "items_cleaned": clean_result.moved,
        "bytes_freed": clean_result.bytes_freed,
        "errors": clean_result.errors,
    }
    entries = load()
    entries.append(entry)
    entries = entries[-MAX_ENTRIES:]
    try:
        Path(HISTORY_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_PATH, "w") as f:
            json.dump(entries, f, indent=2)
    except OSError:
        pass


def load() -> list[dict]:
    """Return all history entries, oldest first."""
    try:
        with open(HISTORY_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def format_history() -> str:
    entries = load()
    if not entries:
        return "No run history found."
    from reporter import format_size
    lines = []
    for e in reversed(entries[-10:]):
        tag = " [dry-run]" if e.get("dry_run") else ""
        freed = format_size(e.get("bytes_freed", 0))
        cleaned = e.get("items_cleaned", 0)
        errors = e.get("errors", 0)
        err_str = f", {errors} error(s)" if errors else ""
        lines.append(f"{e['date']}{tag} — {cleaned} items, {freed} freed{err_str}")
    return "\n".join(lines)
