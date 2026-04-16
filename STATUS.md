# MacMaid — Project Status
_Last updated: 2026-04-16 (Session 4)_

---

## What's Built and Working

- **14 scan modules**: caches, logs, trash, large_files, duplicates, dev_junk, browsers, mail, login_items, disk_health, memory, thermal, ios_backups, xcode_sims
- **Cleaner**: send2trash (default) + permanent delete mode; `CleanResult` includes `moved_paths` for accurate UI state
- **Reporter**: Rich-based terminal UI — panels, tables, progress bar, unattended text report, dry-run header
- **Emailer**: wraps `~/.claude/utils/send_email.py`
- **Scheduler**: installs/removes LaunchAgent plist; `_resolve_python()` prefers active venv; registers `macmaid://` URL scheme on install
- **History**: `history.py` appends JSON entries to `~/Library/Logs/mac-maid-history.json`; `--history` flag shows last 10 runs
- **Main orchestrator**: interactive + unattended modes, `--modules`, `--schedule`, `--dry-run`, `--history`, `--review`
- **Results persistence**: unattended scan saves full results to `~/Library/Logs/mac-maid-last-results.json` (skipped on dry-run)
- **Browser review UI** (`reviewer.py`): local Flask server with tabbed UI — Large & Old Files and Duplicates tabs with lazy loading, per-tab column definitions, badge counts, sortable/filterable table, row-click selection, Move to Trash, Reveal in Finder, sticky headers, pagination (200/page), toast notifications
- **URL scheme** (`url_handler.py`): `macmaid://` custom URL scheme registered via macOS Launch Services; app bundle at `~/.local/share/MacMaid.app`
- **Email review link**: unattended email includes `http://localhost:5888` button when reviewable files (large or duplicate) are found; background Flask server starts during unattended scan
- **pyproject.toml**: project metadata, entry point (`macmaid`), dev extras; flask added as dependency
- **README.md**: setup, all CLI flags, config reference, thermal sudo instructions
- **Full test suite**: 97 tests, all passing
- **GitHub**: https://github.com/kmm2908/MacMaid

---

## Needs Testing (Manual)

- [x] Run full test suite (pytest) — 97/97 passed (Session 4: still 97/97)
- [ ] Run `python main.py` interactively end-to-end — needs manual terminal (questionary uses TTY directly)
- [x] Run `python main.py --unattended --no-email` — scan ran across all 14 modules
- [x] Run `python main.py --unattended --dry-run --no-email` — confirmed exit 0, nothing deleted
- [x] Run `python main.py --history` — confirmed, shows last 5 runs with timestamps/counts
- [x] Run `python main.py --schedule 02:00` — plist installed, URL scheme registered, `~/.local/share/MacMaid.app` created
- [x] Run `python main.py --schedule-status` — confirmed
- [x] Confirm thermal module degrades gracefully without passwordless sudo
- [x] Confirm email report delivery with review link — email now sends HTML with a styled button linking to `http://localhost:5888`
- [x] Click review link in email (Gmail/Chrome) — opens browser UI; server starts as background process during unattended scan and waits until ready before emailing
- [x] Test browser UI end-to-end: filter, sort, select files, Move to Trash, Reveal in Finder — all working; stale entries cleaned gracefully
- [ ] Test Duplicates tab end-to-end: filter, sort, select, Move to Trash — UI confirmed loading (31,441 items); deletion flow not yet manually tested

---

## Deferred / Future

- [ ] **Full browser UI** — move the entire scan/report/clean flow into a browser UI (replace Rich terminal output); all modules surfaced, not just Large & Old Files
- [ ] **Merge CleanUp project** — absorb `/Volumes/Ext Data/VSC Projects/CC Dev/CleanUp/cleanup.py` (Downloads auto-cleaner with Finder tag protection, 24h guard, macOS notifications) as a new MacMaid module; retire the separate CleanUp project
- [ ] Add a `config` subcommand or interactive config editor
- [ ] Consider packaging for pip / Homebrew
- [ ] `--review` and the email review link now cover Large & Old Files + Duplicates; could extend to other `risk=review` modules if added in future
