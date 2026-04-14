# MacMaid — Project Status
_Last updated: 2026-04-14 (Session 3)_

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
- **Browser review UI** (`reviewer.py`): local Flask server with sortable/filterable table, checkboxes, Move to Trash, Reveal in Finder — launched via `--review` flag
- **URL scheme** (`url_handler.py`): `macmaid://` custom URL scheme registered via macOS Launch Services; app bundle at `~/.local/share/MacMaid.app`
- **Email review link**: unattended email includes `macmaid://review` link when large files are found; clicking it opens the browser UI
- **pyproject.toml**: project metadata, entry point (`macmaid`), dev extras; flask added as dependency
- **README.md**: setup, all CLI flags, config reference, thermal sudo instructions
- **Full test suite**: 97 tests, all passing
- **GitHub**: https://github.com/kmm2908/MacMaid

---

## Needs Testing (Manual)

- [x] Run full test suite (pytest) — 97/97 passed
- [ ] Run `python main.py` interactively end-to-end — needs manual terminal (questionary uses TTY directly)
- [x] Run `python main.py --unattended --no-email` — scan ran across all 14 modules
- [x] Run `python main.py --unattended --dry-run --no-email` — confirmed exit 0, nothing deleted
- [ ] Run `python main.py --history` — pending
- [x] Run `python main.py --schedule 02:00` — plist installed, URL scheme registered, `~/.local/share/MacMaid.app` created
- [x] Run `python main.py --schedule-status` — confirmed
- [x] Confirm thermal module degrades gracefully without passwordless sudo
- [ ] Confirm email report delivery with `macmaid://review` link — pending next nightly run
- [ ] Click `macmaid://review` link in email — launches browser UI (URL scheme registered and verified via lsregister)
- [ ] Test browser UI end-to-end: filter, sort, select files, Move to Trash, Reveal in Finder

---

## Deferred / Future

- [ ] Add a `config` subcommand or interactive config editor
- [ ] Consider packaging for pip / Homebrew
- [ ] `--review` currently only surfaces Large & Old Files — could extend to other `risk=review` modules (e.g. duplicates)
- [ ] Browser UI: page refresh after deletion shows deleted items (server state not updated) — benign for single-session use
