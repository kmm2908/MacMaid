# MacMaid — Claude Context

## What This Project Is
A macOS maintenance CLI tool. It scans for junk, reports findings with a Rich terminal UI, and cleans up safely. Supports interactive and unattended (scheduled) modes.

## Architecture

```
main.py          — CLI entry point; orchestrates scan → report → clean flow
config.py        — JSON config loader with defaults; always read inside scan(), never at module level
cleaner.py       — send2trash (default) or permanent delete; returns CleanResult dataclass
reporter.py      — Rich panels/tables/progress; print_unattended_report() for text reports
emailer.py       — thin wrapper around ~/.claude/utils/send_email.py
scheduler.py     — builds and installs LaunchAgent plist; _resolve_python() picks venv Python
history.py       — appends JSON run records to ~/Library/Logs/mac-maid-history.json
modules/         — one file per scan category, all expose scan() -> dict
tests/           — one test file per module; run with pytest (configured in pyproject.toml)
```

## Module Contract
Every `modules/*.py` must expose `scan() -> dict` returning a result from `make_result()`:
- `risk`: `"safe"` | `"review"` | `"inform-only"`
- `action`: `"trash"` | `"empty-trash"` | `"none"`
- `items`: list of `make_item()` dicts

## Current Modules (14)
`caches`, `logs`, `trash`, `large_files`, `duplicates`, `dev_junk`, `browsers`, `mail`, `login_items`, `disk_health`, `memory`, `thermal`, `ios_backups`, `xcode_sims`

Register new modules in the `MODULES` dict at the top of `main.py`.

## Key Rules
- **Config is always read inside `scan()`**, not at module import time — module-level config globals will break tests
- **Thermal requires passwordless sudo** — `_has_passwordless_sudo()` checks first and returns an inform-only result if unavailable
- **Scheduler uses `_resolve_python()`** — prefers active venv, then `.venv`/`venv` in project dir, then `sys.executable`
- **Tests patch at the `module.cfg.get` level**, not via removed module-level constants

## Running Tests
```bash
/Users/fred/Library/Python/3.12/bin/pytest tests/
```
(or activate a venv with pytest installed)

## Config Keys (config.json)
| Key | Default | Used by |
|-----|---------|---------|
| `large_file_threshold_mb` | 500 | large_files |
| `old_file_days` | 180 | large_files |
| `log_retention_days` | 7 | logs |
| `scan_paths` | Downloads/Desktop/Documents | large_files, duplicates |
| `dev_scan_paths` | `~/`, `/Volumes/Ext Data` | dev_junk |
| `email_report_to` | kmmsubs@gmail.com | main (unattended) |
| `permanent_delete` | false | main |
| `modules` | all true | main |
