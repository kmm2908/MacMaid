import json
from pathlib import Path

CONFIG_PATH = str(Path(__file__).parent / "config.json")

DEFAULTS = {
    "large_file_threshold_mb": 500,
    "old_file_days": 180,
    "log_retention_days": 7,
    "scan_paths": ["~/Downloads", "~/Desktop", "~/Documents"],
    "dev_scan_paths": ["~/", "/Volumes/Ext Data"],
    "email_report_to": "kmmsubs@gmail.com",
    "modules": {},
    "permanent_delete": False,
}

_config: dict = {}


def _load() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _reset() -> None:
    global _config
    _config = {}


def get(key: str):
    if not _config:
        _config.update(_load())
    return _config.get(key, DEFAULTS.get(key))


def module_enabled(name: str) -> bool:
    modules = get("modules") or {}
    return modules.get(name, True)


# Reset cache on module load (for testing with reload)
_reset()
