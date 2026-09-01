# MacMaid — Project Status
_Last updated: 2026-09-01_

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
- **`dev_junk` installed-software guard** (2026-09-01): the sweep offers an artefact only when git tracks matching evidence directly in its parent directory, plus deny-lists for install locations and `.app`/`.framework` bundles. Fixes the 2026-08-30 incident where the daily run stripped `node_modules` from six installed VS Code extensions and was also targeting the Codex CLI runtime. Measured on the real roots: 1311 artefacts offered before, 291 now — 527 under `$HOME` down to 1, while 7.32 GB of the original 7.42 GB of genuine project junk is still offered. Failures (no git, hang, exhausted budget) are declined and counted into the result's suggestion. Rule + accepted trade-offs: `CLAUDE.md`
- **Test suite**: 181 tests, all passing, 0 skipped (verified 2026-09-01)
- **Project hygiene** (2026-07-09): `CLAUDE.md`, `.claude/settings.json`, and superpowers design docs added; `.playwright-mcp` scratch + `settings.local.json` gitignored
- **GitHub**: https://github.com/kmm2908/MacMaid

---

## Needs Testing (Manual)

- [ ] Run `python main.py` interactively end-to-end — needs a real terminal (questionary uses the TTY directly)
- [ ] Test Duplicates tab end-to-end: filter, sort, select, Move to Trash — UI confirmed loading (31,441 items); the deletion flow is not yet manually exercised
- [x] Full test suite (pytest) — 181/181, 0 skipped (2026-09-01)
- [x] `--unattended --no-email` scan across all 14 modules
- [x] `--unattended --dry-run --no-email` — exit 0, nothing deleted
- [x] `--history`, `--schedule 02:00` (plist + URL scheme + app bundle), `--schedule-status`
- [x] Thermal degrades gracefully without passwordless sudo
- [x] Email report with review link → opens browser UI (server starts as background process, waits until ready)
- [x] Browser UI (Large & Old Files): filter, sort, select, Move to Trash, Reveal in Finder — all working; stale entries cleaned gracefully

---

## Still Needs Human Input

- Nothing outstanding.

---

## Deferred / Future

- [ ] **`dev_junk` residual risk** — a tool installed by `git clone` + `npm install` into a location no deny-list names is still offered for cleanup; only location distinguishes it from a project. Narrowing `dev_scan_paths` was ruled out (it would lose real cleanup under `~` and regress the moment someone widens it again). Revisit only if it bites.
- [ ] **`dev_junk` no longer cleans venv bytecode** — `__pycache__` under `.venv`/`site-packages`, and any project living under `~/bin`, `~/opt`, `~/go`, `~/.config` or `~/Library`, are deliberately skipped. Costs ~0.08 GB on this machine; the trade-off is pinned by a test.
- [ ] **Full browser UI** — move the entire scan/report/clean flow into the browser (replace Rich terminal output); surface all modules, not just Large & Old Files + Duplicates
- [ ] **Merge the CleanUp project** — absorb `../CleanUp/cleanup.py` (Downloads auto-cleaner: Finder-tag protection, 24h guard, macOS notifications) as a new MacMaid module and retire the standalone CleanUp project
- [ ] Add a `config` subcommand or interactive config editor
- [ ] Consider packaging for pip / Homebrew
- [ ] Extend `--review` / email review link to any future `risk=review` modules beyond Large & Old Files + Duplicates
