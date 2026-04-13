# MacMaid — Project Status
_Last updated: 2026-04-13 (Session 2)_

---

## What's Built and Working

- **14 scan modules**: caches, logs, trash, large_files, duplicates, dev_junk, browsers, mail, login_items, disk_health, memory, thermal, ios_backups, xcode_sims
- **Cleaner**: send2trash (default) + permanent delete mode
- **Reporter**: Rich-based terminal UI — panels, tables, progress bar, unattended text report, dry-run header
- **Emailer**: wraps `~/.claude/utils/send_email.py`
- **Scheduler**: installs/removes LaunchAgent plist; `_resolve_python()` prefers active venv
- **History**: `history.py` appends JSON entries to `~/Library/Logs/mac-maid-history.json`; `--history` flag shows last 10 runs
- **Main orchestrator**: interactive + unattended modes, `--modules`, `--schedule`, `--dry-run`, `--history`
- **pyproject.toml**: project metadata, entry point (`macmaid`), dev extras
- **README.md**: setup, all CLI flags, config reference, thermal sudo instructions
- **Full test suite**: 77 tests, all passing
- **GitHub**: https://github.com/kmm2908/MacMaid

---

## Needs Testing (Manual)

- [x] Run full test suite (pytest) — 77/77 passed (Python 3.12, pytest 9.0.3)
- [ ] Run `python main.py` interactively end-to-end — needs manual terminal (questionary uses TTY directly)
- [x] Run `python main.py --unattended --no-email` — scan ran across all 14 modules; clean phase ran (13K+ files moved to Trash)
- [x] Run `python main.py --unattended --dry-run --no-email` — confirmed exit 0, nothing deleted
- [ ] Run `python main.py --history` — pending
- [ ] Run `python main.py --schedule 02:00` — confirm LaunchAgent plist is created and loaded
- [ ] Run `python main.py --schedule-status` and `--unschedule`
- [x] Confirm thermal module degrades gracefully when run without passwordless sudo — "Thermal data unavailable / powermetrics returned no data" shown correctly
- [ ] Confirm email report delivery via `python main.py --unattended`

---

## Deferred / Future

- [ ] Add a `config` subcommand or interactive config editor
- [ ] Add `No virtual environment documented` note to README (which Python to use)
- [ ] Consider packaging for pip / Homebrew
