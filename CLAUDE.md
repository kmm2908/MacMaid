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
reviewer.py      — Flask local server + embedded HTML/JS browser review UI; start(categories) is the entry point; categories is dict[str, list[dict]] keyed by category name
url_handler.py   — creates ~/.local/share/MacMaid.app bundle and registers macmaid:// URL scheme via lsregister
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
- **`reviewer.py` embeds JS in a Python triple-quoted string** — `\'` inside `"""..."""` is just `'`, not an escaped quote; use `data-*` attributes + `addEventListener` instead of inline `onclick` handlers to avoid JS syntax errors
- **`save_results()` is skipped in dry-run mode** — `unattended_mode()` only writes `mac-maid-last-results.json` when `dry_run=False`
- **`--schedule` registers the URL scheme** — re-run `--schedule` after a fresh install to create `~/.local/share/MacMaid.app` and register `macmaid://`

## Running the App
```bash
# Run main.py — must use this interpreter (has all deps installed):
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 main.py [flags]

# Key flags:
#   --unattended        silent scan + email report (saves results JSON for --review)
#   --dry-run           scan without cleaning (does NOT save results JSON)
#   --review            open browser UI for last saved scan results
#   --schedule HH:MM    install LaunchAgent + register macmaid:// URL scheme
```

## Running Tests
```bash
/Users/fred/Library/Python/3.12/bin/pytest tests/
```
(pytest shebang resolves to `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`)

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
