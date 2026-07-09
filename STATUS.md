# MacMaid — Project Status
_Last updated: 2026-07-09_

---

## What This Is
A macOS maintenance CLI: scans for junk across 14 categories, reports findings in a Rich terminal UI (or a browser review UI), and cleans up safely (send2trash by default). Supports interactive and unattended/scheduled modes. See `CLAUDE.md` for architecture and the module contract.

## What's Built and Working

- **14 scan modules**: `caches`, `logs`, `trash`, `large_files`, `duplicates`, `dev_junk`, `browsers`, `mail`, `login_items`, `disk_health`, `memory`, `thermal`, `ios_backups`, `xcode_sims` (each exposes `scan() -> dict` via `modules/base.py` helpers)
- **Cleaner**: send2trash (default) + permanent delete mode; `CleanResult` includes `moved_paths` for accurate UI state
- **Reporter**: Rich terminal UI — panels, tables, progress bar, unattended text report, dry-run header
- **Emailer**: wraps `~/.claude/utils/send_email.py`
- **Scheduler**: installs/removes LaunchAgent plist; `_resolve_python()` prefers active venv; registers `macmaid://` URL scheme on install
- **History**: `history.py` appends JSON run records to `~/Library/Logs/mac-maid-history.json`; `--history` shows recent runs
- **Main orchestrator**: interactive + unattended modes; flags `--modules`, `--schedule`, `--schedule-status`, `--dry-run`, `--history`, `--review`, `--unattended`, `--no-email`
- **Results persistence**: unattended scan saves full results to `~/Library/Logs/mac-maid-last-results.json` (skipped on dry-run)
- **Browser review UI** (`reviewer.py`): local Flask server, tabbed UI (Large & Old Files + Duplicates) — lazy loading, per-tab columns, badge counts, sortable/filterable table, row-click selection, Move to Trash, Reveal in Finder, sticky headers, pagination (200/page), toasts
- **URL scheme** (`url_handler.py`): `macmaid://` registered via Launch Services; app bundle at `~/.local/share/MacMaid.app`
- **Email review link**: unattended email includes a `http://localhost:5888` button when reviewable files (large or duplicate) are found; Flask server starts during the unattended scan
- **pyproject.toml**: metadata, `macmaid` entry point, dev extras, flask dependency
- **README.md**: setup, all CLI flags, config reference, thermal sudo instructions
- **Test suite**: 97 tests, all passing (verified 2026-07-09)
- **Project hygiene** (2026-07-09): `CLAUDE.md`, `.claude/settings.json`, and superpowers design docs added; `.playwright-mcp` scratch + `settings.local.json` gitignored
- **GitHub**: https://github.com/kmm2908/MacMaid

---

## Needs Testing (Manual)

- [ ] Run `python main.py` interactively end-to-end — needs a real terminal (questionary uses the TTY directly)
- [ ] Test Duplicates tab end-to-end: filter, sort, select, Move to Trash — UI confirmed loading (31,441 items); the deletion flow is not yet manually exercised
- [x] Full test suite (pytest) — 97/97
- [x] `--unattended --no-email` scan across all 14 modules
- [x] `--unattended --dry-run --no-email` — exit 0, nothing deleted
- [x] `--history`, `--schedule 02:00` (plist + URL scheme + app bundle), `--schedule-status`
- [x] Thermal degrades gracefully without passwordless sudo
- [x] Email report with review link → opens browser UI (server starts as background process, waits until ready)
- [x] Browser UI (Large & Old Files): filter, sort, select, Move to Trash, Reveal in Finder — all working; stale entries cleaned gracefully

---

## Deferred / Future

- [ ] **Full browser UI** — move the entire scan/report/clean flow into the browser (replace Rich terminal output); surface all modules, not just Large & Old Files + Duplicates
- [ ] **Merge the CleanUp project** — absorb `../CleanUp/cleanup.py` (Downloads auto-cleaner: Finder-tag protection, 24h guard, macOS notifications) as a new MacMaid module and retire the standalone CleanUp project
- [ ] Add a `config` subcommand or interactive config editor
- [ ] Consider packaging for pip / Homebrew
- [ ] Extend `--review` / email review link to any future `risk=review` modules beyond Large & Old Files + Duplicates
