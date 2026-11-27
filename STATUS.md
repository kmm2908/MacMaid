# MacMaid — Project Status
_Last updated: 2026-11-27_

---

## Where It Lives — read this before moving the folder
Moved to `CC Dev/_running/MacMaid` on 2026-09-04: development is finished, the nightly
LaunchAgent is what keeps it alive. Unlike CleanUp, **nothing runs from a copy** — the
`com.macmaid.nightly` plist and the `macmaid://` handler at `~/.local/share/MacMaid.app`
both name this directory, so moving the folder breaks the 02:00 run and the review link
until `main.py --schedule HH:MM` is re-run from the new location. `install()` calls
`launchctl load`, which errors when the label is already loaded — `--unschedule` (or
`launchctl unload`) first, or the reinstall silently returns False and the URL handler is
never rewritten. `trello sync`/`add`/`promote`/`open` cannot see `_running/` projects
(Trello board card `zT2GhMnv`), so the `ToDo.md` mirror here will go stale.

## What This Is
A macOS maintenance CLI: scans for junk across 15 categories, reports findings in a Rich terminal UI (or a browser review UI), and cleans up safely (send2trash by default). Supports interactive and unattended/scheduled modes. See `CLAUDE.md` for architecture and the module contract.

## What's Built and Working

- **15 scan modules** (`downloads` is off by default; the CleanUp cron still does that job): `caches`, `logs`, `trash`, `downloads`, `large_files`, `duplicates`, `dev_junk`, `browsers`, `mail`, `login_items`, `disk_health`, `memory`, `thermal`, `ios_backups`, `xcode_sims` (each exposes `scan() -> dict` via `modules/base.py` helpers)
- **Cleaner**: send2trash (default) + permanent delete mode; `CleanResult` includes `moved_paths` for accurate UI state
- **Trash retention counts from binned time** (2026-11-27, card guPNotLn): entries are emptied 7 days after they reached the Trash (Date Added), not after their last edit; a later write inside restarts the count; hard links and unknown dates are kept
- **Trash scan says what it could not check** (2026-11-27, card WNAOOKwI): an unopenable Trash folder, or items with no reliable binned date or not fully readable, are named in the report instead of "nothing has been in the Trash longer than 7 days"
- **Reporter**: Rich terminal UI — panels, tables, progress bar, unattended text report, dry-run header
- **Emailer**: wraps `~/.claude/utils/send_email.py`
- **Scheduler**: installs/removes LaunchAgent plist; `_resolve_python()` prefers active venv; registers `macmaid://` URL scheme on install
- **History**: `history.py` appends JSON run records to `~/Library/Logs/mac-maid-history.json`; `--history` shows recent runs
- **Main orchestrator**: interactive + unattended modes; flags `--modules`, `--schedule`, `--schedule-status`, `--dry-run`, `--history`, `--review`, `--unattended`, `--no-email`
- **`config` subcommand** (2026-11-27, card EyNoGPT2): `main.py config` lists every setting; `get` / `set` / `unset` change one (`config_cli.py`). Unknown keys and nonsense values are refused, and a damaged `config.json` is never rewritten
- **Results persistence**: unattended scan saves full results to `~/Library/Logs/mac-maid-last-results.json` (skipped on dry-run)
- **Browser review UI** (`reviewer.py`): local Flask server, one tab per trashable review category with results (Large & Old Files, Duplicates, Mail Store, iOS Backups; the last two carry a caution line and a stronger confirm box, and are left alone if anything inside changed since the scan) — lazy loading, per-tab columns, badge counts, sortable/filterable table, row-click selection, Move to Trash, Reveal in Finder, sticky headers, pagination (200/page), toasts. Refuses non-localhost `Host` names; delete, reveal and quit need that session's token (a page left open from an earlier run says to reload)
- **Disk alert can be given Full Disk Access on its own** (2026-11-27, card 5YhIqK1s, choices: a MacMaid launcher; hourly alert only): `--schedule` now builds `~/.local/share/MacMaid Storage Check.app` and the hourly agent runs it. Probed from launchd before any grant: Trash, Mail and iPhone backups blocked, Caches partly readable, Documents, Downloads and Desktop readable. The nightly clean is unchanged and still cannot see Trash or Mail
- **Browser app** (2026-11-27, card lniVMHcS, choices 1A 2A 3A): `python main.py` now opens the browser, which starts a scan at once with progress per category, then shows a Summary tab (every category, what happens to it, items, size) and one tab per category with results. Safe and review categories are ticked and moved to the Trash; the Trash tab empties old entries behind its own confirmation; information categories have no delete control; Scan again reruns it. Apart from emptying old Trash, the browser never deletes permanently. The terminal flow stays behind `--terminal` (and `--permanent`). The server now hands each item to the cleaner with its category's action and refuses a POST from a non-localhost Origin. Nightly run and email unchanged. `--dry-run` without `--unattended` is now refused, and `permanent_delete: true` keeps the terminal. Found while testing it on this Mac: the Duplicates scan read iCloud-only files in Documents (27,909 of them), which downloads each one, and a stalled download hung the scan for 30 minutes; it now skips them and says how many
- **URL scheme** (`url_handler.py`): `macmaid://` registered via Launch Services; app bundle at `~/.local/share/MacMaid.app`
- **Email review link**: unattended email includes a `http://localhost:5888` button when any trashable review category has items; Flask server starts during the unattended scan
- **pyproject.toml**: metadata, `macmaid` entry point, dev extras, flask dependency
- **README.md**: setup, all CLI flags, config reference, thermal sudo instructions
- **`dev_junk` installed-software guard** (2026-09-01): the sweep offers an artefact only when git tracks matching evidence directly in its parent directory, plus deny-lists for install locations and `.app`/`.framework` bundles. Fixes the 2026-08-30 incident where the daily run stripped `node_modules` from six installed VS Code extensions and was also targeting the Codex CLI runtime. Measured on the real roots: 1311 artefacts offered before, 291 now — 527 under `$HOME` down to 1, while 7.32 GB of the original 7.42 GB of genuine project junk is still offered. Failures (no git, hang, exhausted budget) are declined and counted into the result's suggestion. Rule + accepted trade-offs: `CLAUDE.md`
- **`dev_junk` dormancy gate** (2026-09-08): `node_modules` is offered only when the repository holding it has had no commit for `dev_junk_dormant_days` (default 180) **and** nothing locally says otherwise — the mtime of the project directory and every immediate entry in it (`.git` excluded, or the module's own git calls look like work), plus `git status`. The 2026-09-01 guard kept a `node_modules` whenever git tracked `package.json` beside it, which selected live projects rather than sparing them; one lost the same directory eight times and 519 had piled up in `/Volumes/Ext Data/.Trashes/501/`. The scan now also records the directory's mtime before deciding and `cleaner` re-checks it before deleting, so nothing installed between the scan and the clean is taken. Verified on the real roots: all 22 live projects spared (DeckForge, SiteBuilder's 20 workspaces, GHL-Clone), a planted 700-day-dormant checkout still offered, 0 directories git could not answer for. Two Codex review rounds: round 1 raised 1 Critical (an old commit date is not proof of local inactivity), round 2 raised 3 more (top-level-only re-check, baseline read after the size walk, untracked work invisible) — all fixed or pinned as documented limits. `tools/redproof_dev_junk.py` proves the tests can fail: 18 mutants, all caught (14 originally; 4 added 2026-11-27 with card OpCUFRxY, which made recently written untracked work in subdirectories count and cached the git answers per repository root). Rule + accepted trade-offs: `CLAUDE.md`
- **Low-storage warning** (2026-11-05): `storage_watch.py` runs hourly from its own LaunchAgent (`com.macmaid.storage`, installed and confirmed loaded and exiting 0). Below 25 GB free it emails (`--action`) and shows a notification; below 10 GB the email goes `--urgent`. The body lists Trash first, then the largest of Downloads, Caches, Developer, iPhone backups, Mail, Desktop and Documents. Prompted by the Data volume hitting 4.7 GB free on 2026-11-05, when macOS kept force-quitting RoboForm to reclaim space. Not built: watching the unified log for `CacheDeleteAppContainerCaches` terminations. 2026-11-27: under launchd macOS refuses Trash, Mail and iPhone backups (no Full Disk Access, measured); the alert now says so, shows partly readable folders as "at least N GB" and counts local Time Machine snapshots. The on-screen banner had never been able to show (AppleScript refused the escaped dash in its title, and the failure was swallowed); fixed 2026-11-27, and a refused banner is now logged. Re-runnable proof: `tests/test_storage_watch_e2e.py` drives `--storage-check` through the real `main.main()` with the thresholds moved (sender and `osascript` stood in, nothing sent or shown), compiles the banner script and checks the installed sender lists every option used. A delivered email and a banner on screen from launchd are still unseen live
- **Readable review UI and email** (2026-11-27, card 5hkxisKU): both are dark, 24px minimum, canonical buttons (every report email is now HTML, with or without the review button). The page takes its colours from `tokens.css` (copied whole from the dashboard-ui skill); the email inlines the same hexes. `tests/test_ui_contrast.py` renders six states of the page and the email in headless Chrome and fails on any breach, so the suite now needs Playwright and Google Chrome
- **Duplicates tab tested end-to-end** (2026-11-27, card js35p4gA): one-off run with a real scan, real Chrome and real Trash on throwaway files (the committed tests mock the cleaner). Fixed: a symlink, hard link or overlapping scan path could offer a file's only copy as its duplicate; a file listed in both tabs stayed in one after trashing; the confirm box now counts selected files hidden by the filter; an empty filter reads `0 of 0`; a duplicate is refused if the copy it duplicates is gone or changed by the time you click
- **Safer Enter key** (2026-11-27, card RHA8A2iF): in interactive mode a bare Enter now answers No for emptying the Trash, for each reviewed file and for every deletion under `--permanent`; cleaning a whole safe category into the Trash, and opening a review, still default to Yes. `dev_junk` now reads `dev_scan_paths` when it scans, not at import
- **Test suite**: 455 tests, all passing, 0 skipped (verified 2026-11-27)
- **Project hygiene** (2026-07-09): `CLAUDE.md`, `.claude/settings.json`, and superpowers design docs added; `.playwright-mcp` scratch + `settings.local.json` gitignored
- **GitHub**: https://github.com/kmm2908/MacMaid

---

## Needs Testing (Manual)

- [x] Run `python main.py` interactively end-to-end — done 2026-11-27 (4J1ymHNX): driven in a pseudo-terminal (`tests/test_interactive_e2e.py`). Fixed: Ctrl-C moved on to the next prompt instead of stopping; a file trashed in one review was offered again in the next; failures (Trash emptying included) never reached the error log; `[..]` in file names was not shown; `--permanent` still asked "Move to Trash?"
- [x] Test Duplicates tab end-to-end — done 2026-11-27 (js35p4gA)
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
- [ ] **Full browser UI** — move the entire scan/report/clean flow into the browser (replace Rich terminal output); surface all modules, not just the review categories
- [ ] **Retire the standalone CleanUp project** (`../_running/CleanUp`) — its cleaner is now `modules/downloads.py` (2026-11-27), reported through the nightly email in place of a macOS notification. Switch-over waits on the owner: set `modules.downloads` to `true`, remove the 06:00 `cleanup.py` crontab line, mark CleanUp retired
- [ ] Add a `config` subcommand or interactive config editor
- [ ] Consider packaging for pip / Homebrew
- [x] Extend `--review` / email review link to every trashable `risk=review` module — done 2026-11-27 (N1G8HJ0O)
