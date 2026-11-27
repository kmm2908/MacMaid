"""`main.py config` — view and change config.json.

The nightly run deletes files according to these settings, so a value that cannot
be understood is refused, and a damaged config.json is never rewritten.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from typing import Any

import config as cfg
from modules.dev_junk import DORMANT_DAYS_DEFAULT

WHOLE_NUMBER_KEYS = {"large_file_threshold_mb", "old_file_days", "log_retention_days",
                     "trash_retention_days", "dev_junk_dormant_days"}
NUMBER_KEYS = {"storage_warn_gb", "storage_urgent_gb", "storage_realert_hours"}
PATH_LIST_KEYS = {"scan_paths", "dev_scan_paths"}
THRESHOLD_KEYS = {"storage_urgent_gb", "storage_warn_gb"}
BOOL_KEYS = {"permanent_delete"}
TEXT_KEYS = {"email_report_to"}
KEYS = sorted(WHOLE_NUMBER_KEYS | NUMBER_KEYS | PATH_LIST_KEYS | BOOL_KEYS | TEXT_KEYS)
MODULE_PREFIX = "modules."
MAX_NUMBER = 100_000  # far past any real setting; bigger values overflow date arithmetic
EMAIL = re.compile(r"[^@\s]+@[^@\s]+")


def _check_key(key: str, module_names: Sequence[str]) -> None:
    if key in KEYS or key in [MODULE_PREFIX + name for name in module_names]:
        return
    raise ValueError(f"unknown setting '{key}'. Run `config` to list them all.")


def _problem(key: str, value: object) -> str | None:
    """What a good value looks like, when this one is not good; otherwise None."""
    if key in BOOL_KEYS or key.startswith(MODULE_PREFIX):
        return None if isinstance(value, bool) else "true or false"
    if key in PATH_LIST_KEYS:
        # The nightly job has no useful working directory, so a relative path means nothing.
        # An unknown ~name stays unexpanded, and an empty list makes the scans use their own.
        ok = isinstance(value, list) and bool(value) and all(
            isinstance(v, str) and v.startswith(("/", "~"))
            and os.path.expanduser(v).startswith("/") for v in value)
        return None if ok else "full paths (/, ~ or ~username of a real user), at least one"
    if key in TEXT_KEYS:
        ok = value == "" or (isinstance(value, str) and value.isprintable()
                             and EMAIL.fullmatch(value) is not None)
        return None if ok else "an email address, or '' to send no report"
    whole = key in WHOLE_NUMBER_KEYS
    ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
          and 0 < value <= MAX_NUMBER and not (whole and value != int(value)))
    kind = "a whole number" if whole else "a number"
    return None if ok else f"{kind} above 0 and no more than {MAX_NUMBER}"


def _typed(key: str, text: str) -> object:
    """Command-line text as the JSON value it stands for; unchanged when it stands for none."""
    if key in BOOL_KEYS or key.startswith(MODULE_PREFIX):
        return {"true": True, "false": False}.get(text.lower(), text)
    if key in TEXT_KEYS:
        return text
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _parse(key: str, values: list[str]) -> object:
    if key not in PATH_LIST_KEYS and len(values) != 1:
        raise ValueError(f"{key} takes exactly one value, got {len(values)}.")
    value = values if key in PATH_LIST_KEYS else _typed(key, values[0])
    wanted = _problem(key, value)
    if wanted:
        raise ValueError(f"{key} must be {wanted}, not '{' '.join(values)}'.")
    return value


def _remedy(key: str) -> str:
    """How to clear a bad value; unset is refused for a threshold when the default would invert."""
    unset = f"`config unset {key}`"
    return f"`config set {key} <number>` or {unset}" if key in THRESHOLD_KEYS else unset


def _check_file(data: dict[str, Any], module_names: Sequence[str]) -> None:
    """Refuse to rewrite settings that hold a bad value; "false" in quotes reads as true."""
    entries = {key: data[key] for key in KEYS if key in data}
    modules = data.get("modules", {})
    entries |= {MODULE_PREFIX + n: modules[n] for n in module_names if n in modules}
    for key, value in entries.items():
        wanted = _problem(key, value)
        if wanted:
            raise ValueError(f"{cfg.CONFIG_PATH} has {key} = {json.dumps(value)}, which must be "
                             f"{wanted}. Run {_remedy(key)} first.")


def _bad_value(data: dict[str, Any], key: str) -> str | None:
    """The stored value and what it should be, when the file holds a bad one for key."""
    section = data.get("modules", {}) if key.startswith(MODULE_PREFIX) else data
    name = key.removeprefix(MODULE_PREFIX)
    wanted = _problem(key, section[name]) if name in section else None
    return f"{key} = {json.dumps(section[name])}  (INVALID: must be {wanted})" if wanted else None


def _check_thresholds(data: dict[str, Any], hint: str) -> None:
    levels: dict[str, Any] = {}
    for key in ("storage_urgent_gb", "storage_warn_gb"):
        value = data.get(key, cfg.DEFAULTS[key])
        levels[key] = cfg.DEFAULTS[key] if _problem(key, value) else value
    if levels["storage_urgent_gb"] > levels["storage_warn_gb"]:
        raise ValueError("storage_urgent_gb ({storage_urgent_gb}) cannot be above "
                         "storage_warn_gb ({storage_warn_gb}).".format(**levels) + hint)


def _threshold_hint(key: str, removing: bool) -> str:
    if key not in THRESHOLD_KEYS:
        return " Change one of them with `config set` first."
    return f" Give {key} a value with `config set` instead." if removing else ""


def _read_file() -> dict[str, Any]:
    try:
        with open(cfg.CONFIG_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"{cfg.CONFIG_PATH} is not valid JSON ({exc}). Fix it first.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("modules", {}), dict):
        raise ValueError(f"{cfg.CONFIG_PATH} does not hold the expected settings. Fix it first.")  # noqa: TRY004 - run() reports it
    return data


def _write_file(data: dict[str, Any]) -> None:
    """Replace config.json in one step, so a run starting now never reads half a file."""
    target = os.path.realpath(cfg.CONFIG_PATH)
    mode = os.stat(target).st_mode & 0o777 if os.path.exists(target) else 0o644
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    cfg._reset()


def _changed(data: dict[str, Any], key: str, values: list[str] | None) -> dict[str, Any]:
    """A copy of data with key set to values, or removed when values is None."""
    name = key.removeprefix(MODULE_PREFIX)
    is_module = key.startswith(MODULE_PREFIX)
    section = dict(data.get("modules", {})) if is_module else dict(data)
    if values is None:
        section.pop(name, None)
    else:
        section[name] = _parse(key, values)
    return {**data, "modules": section} if is_module else section


def _value(key: str) -> str:
    if key.startswith(MODULE_PREFIX):
        return json.dumps(bool(cfg.module_enabled(key.removeprefix(MODULE_PREFIX))))
    value = cfg.get(key)
    if value is None and key == "dev_junk_dormant_days":
        value = DORMANT_DAYS_DEFAULT
    return json.dumps(value)


def _show(module_names: Sequence[str]) -> None:
    data = _read_file()
    print(f"Settings file: {cfg.CONFIG_PATH}")
    for key in KEYS + [MODULE_PREFIX + name for name in module_names]:
        name = key.removeprefix(MODULE_PREFIX)
        section = data.get("modules", {}) if key.startswith(MODULE_PREFIX) else data
        mark = "" if name in section else "  (default)"
        # A bad value is shown as stored: the app may read "false" in quotes as true.
        print(_bad_value(data, key) or f"{key} = {_value(key)}{mark}")


def run(argv: list[str], module_names: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="main.py config", description="View or change settings.")
    actions = parser.add_subparsers(dest="action")
    actions.add_parser("show", help="List every setting (the default action)")
    actions.add_parser("get", help="Print one setting").add_argument("key")
    set_parser = actions.add_parser("set", help="Change one setting")
    set_parser.add_argument("key", help="e.g. old_file_days or modules.thermal")
    set_parser.add_argument("values", nargs="+", help="Path settings accept several")
    actions.add_parser("unset", help="Go back to the default").add_argument("key")
    args = parser.parse_args(argv)

    cfg._reset()
    try:
        if args.action in (None, "show"):
            _show(module_names)
            return 0
        _check_key(args.key, module_names)
        data = _read_file()
        bad = _bad_value(data, args.key)
        if args.action == "get" and bad:
            raise ValueError(f"{bad}. Run {_remedy(args.key)}.")
        if args.action != "get":
            values = args.values if args.action == "set" else None
            changed = _changed(data, args.key, values)
            # Removing a bad value is let through, or two of them could never be cleared.
            if not (values is None and bad):
                _check_file(changed, module_names)
            # Correcting some other bad value must not wait for the thresholds.
            if args.key in THRESHOLD_KEYS or not bad:
                _check_thresholds(changed, _threshold_hint(args.key, values is None))
            _write_file(changed)
        print(f"{args.key} = {_value(args.key)}" if args.action != "get" else _value(args.key))
    except (ValueError, OSError) as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 1
    return 0
