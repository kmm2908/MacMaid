<!-- GENERATED FROM TRELLO — do not edit. Board 6a8724fa3e644cd94e6f0a61 · fetched 2026-11-27T17:40Z
     Cards: 32 · renderer v1 · Regenerate: trello sync MacMaid -->

# MacMaid — backlog

The board is authoritative: https://trello.com/b/aFzZdqPQ/macmaid

Edits here are discarded on the next `trello sync`. To change something, move the
card, or run `trello work MacMaid <ref>` / `trello done MacMaid <ref>` —
the ref is the code after `card:` at the end of its line.

## Backlog

- [ ] Take macmaid-module skill into this project `⏸ ON HOLD` <!-- card:MIejKKak -->
      - Next: copy ~/.claude/skills/macmaid-module into .claude/skills here. Setup audit change 8 (General/setup-audit-2026-10-18.html): this skill is global but only this project uses it, and it loads into every Claude session's skill list. Copy it from ~/.claude/skills into this project's .claude/skills, commit, then tell a General or ~/.claude session to remove the global copy. Logged from General, which does not write into other projects.
- [ ] Watch system log for apps force-quit to free disk space `⏸ ON HOLD` <!-- card:svHiPtA7 -->
      Deliberately not built with XdqURsS7 (2026-11-05). Build only if an app is force-quit while ~/Library/Logs/mac-maid-storage-state.json says ok. Measured: 39 CacheDeleteAppContainerCaches events in the last 2 days, RoboForm the main victim, the latest at 18:19 on 2026-11-05 alongside an urgency-3 purge on /System/Volumes/Data, i.e. the disk was genuinely low then, which the hourly free-space check now catches. Cost: a 1-hour 'log show' query takes ~21s CPU, so running it hourly is not free. Gotcha: in zsh call /usr/bin/log, the bare 'log' is a shell builtin.
## Doing

- [ ] Merge the `CleanUp` project — absorb `CC Dev/CleanUp/cleanup.py` (Downloads <!-- card:3yHbtDtc -->
      **✔ Decided 2026-11-27:** A — Switch over now: turn the Downloads module on, remove the 06:00 job, retire the CleanUp project. Right pick because the blocking fix has landed and the old rules are copied exactly. If anything looks wrong, the old script is still on disk and its schedule can be put back.
      auto-cleaner with Finder-tag protection, 24h guard, notifications) as a new MacMaid
      module, then retire the standalone CleanUp project.
## Done

- [x] Consider packaging for pip / Homebrew. <!-- card:iR9xDyTm -->
      **✔ Decided 2026-11-27:** C — Do not package it. Remove the unused command entry and close the card. Right if running it from the project folder is fine, since the nightly job already works that way.
- [x] Codex review of today's commits — findings <!-- card:8YIyT25R -->
      Codex adversarial review of everything committed to MacMaid on 2026-11-27.
      Read-only review: Codex proposed nothing and changed nothing.
      `*****************************`
      \## Critical
      - [modules/downloads.py:80](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/modules/downloads.py:80>), [modules/trash.py:44](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/modules/trash.py:44>), [cleaner.py:96](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/cleaner.py:96>) — A 30-day-old `report.pdf` moved tonight is permanently purged next night because Trash age reuses its mtime. Fix both Trash checks to use recorded Trash-arrival time.
      - [modules/dev_junk.py:311](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/modules/dev_junk.py:311>) — After package A caches “clean,” editing `B/src/app.js` can still let B’s `node_modules` be deleted. Revalidate repository activity immediately before cleaning.
      - [reviewer.py:369](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/reviewer.py:369>) — Selecting the single Mail row moves all `~/Library/Mail`, including local-only messages, after a generic confirmation. Exclude Mail or explicitly confirm whole-folder/local-mail loss.
      - [modules/downloads.py:35](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/modules/downloads.py:35>) — Red-tagging `~/Downloads` itself fails to protect any child. Include the root in ancestor checks.
      \## Should-fix
      - [config_cli.py:197](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/config_cli.py:197>) — With urgent=30 and warn=20, setting `old_file_days=90` preserves the invalid pair. Run cross-setting validation after every mutation.
      - [modules/dev_junk.py:296](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/modules/dev_junk.py:296>) — An old untracked million-file build tree can stall the nightly scan indefinitely. Apply a traversal deadline and fail closed.
      - [main.py:165](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/main.py:165>) — Delete an old duplicate under Large Files; Duplicates still offers it because review moves are not accumulated. Extend `moved_paths` in the review branch.
      - Next: close this tab — everything here is finished.
- [x] STATUS.md contradicts the repo after today's commits <!-- card:n6reLqqF -->
      `*****************************`
      Not accurate; audited the seven listed commits at HEAD `764a321`, excluding staged work.
      \## Critical
      - “Moved to `CC Dev/_running/MacMaid`” — the live LaunchAgent plist and MacMaid app executable point to `CC Dev/MacMaid`.
      - “`--unschedule` … first” — `scheduler.py` unloads before loading.
      - “Add a `config` subcommand” — `main.py` and `config_cli.py` implement it.
      - “Extend `--review` … every trashable `risk=review` module” — committed `main.py` still whitelists two categories; `reviewer.py` lacks Mail/iOS handling.
      - “345 tests” — committed `tests/*.py` collect 337; the dirty tree collects 352.
      \## Should-fix
      - “181/181” and “all 14 modules” — `tests/*.py` and `main.py` now show 337 and 15.
      - Next: close this tab — everything here is finished.
- [x] STATUS.md contradicts the repo after today's commits <!-- card:dcH8rFvw -->
      \## Critical
      > - **`dev_junk` installed-software guard** (2026-09-01): the sweep offers an artefact only when git tracks matching evidence directly in its parent directory, plus deny-lists for install locations and `.app`/`.framework` bundles. Fixes the 2026-08-30 incident where the daily run stripped `node_modules` from six installed VS Code extensions and was also targeting the Codex CLI runtime. Measured on the real roots: 1311 artefacts offered before, 291 now — 527 under `$HOME` down to 1, while 7.32 GB of the original 7.42 GB of genuine project junk is still offered. Failures (no git, hang, exhausted budget) are declined and counted into the result's suggestion. Rule + accepted trade-offs: `CLAUDE.md`
      [modules/dev_junk.py](/Volumes/Ext%20Data/VSC%20Projects/CC%20Dev/MacMaid/modules/dev_junk.py:252) contradicts the universal claim. `scan()` adds Xcode DerivedData, the pip cache, and the npm cache unconditionally, bypassing the git-evidence guard, deny-lists, and even `is_removable()`.
      \## Should-fix
      None. The 181-test count and the remaining newly documented trade-offs agree with the landed commits.
- [x] Disk alert can't measure Trash, Caches, Mail, Documents or iPhone backups <!-- card:5YhIqK1s -->
      Ticket 27e3 (2026-11-24 16:35): the low-disk alert listed five of seven folders as 'could not be measured', so it pointed at nothing — Trash alone held 30 GB. Likely the scheduled run lacks Full Disk Access for ~/.Trash and ~/Library. Also: the alert should mention Time Machine local snapshots — deleting 25 GB freed nothing until they were thinned (17 → 58 GB free).
      **Note 2026-11-27:** Built: hourly check now runs ~/.local/share/MacMaid Storage Check.app (only runs the check; fixed environment; hardened runtime). Probed from launchd 2026-11-27: Trash, Mail, iPhone backups still blocked — waiting on the Full Disk Access grant to that app (System Settings > Privacy & Security > Full Disk Access > + > Cmd+Shift+G, paste the path). Then Claude re-probes and closes this card.
      **Note 2026-11-27:** Verified 2026-11-27 from launchd after the grant: Trash 10.1 GB, Mail 0.3 GB, iPhone backups 0.0 GB measured; Caches partly (Apple-protected). Hourly agent exits 0.
- [x] Full browser UI — move the entire scan/report/clean flow into the browser (replace <!-- card:lniVMHcS -->
      **✔ Decided 2026-11-27:** A — Full plan, as recommended. Running MacMaid opens the browser, with a Scan button and progress for each category. You can select junk and review items and move them to the Trash. Emptying old Trash needs its own confirmation. The old terminal screens stay behind a --terminal switch as a fallback. Permanent delete stays terminal-only. Right pick if you want the whole flow in the browser and still want a way back.
      the Rich terminal output), surfacing all modules, not just Large & Old Files.
      **Note 2026-11-27:** Built 1A 2A 3A in 4286b15 (pushed): python main.py opens the browser app — scan with progress, summary, every category, Trash-only deletes, old Trash emptied behind its own confirm; --terminal keeps the old flow. Also fixed Duplicates hanging 30 min on iCloud-only files. Try it: python main.py
- [x] Codex review of today's commits — findings <!-- card:tP8RVqby -->
      Codex adversarial review of everything committed to MacMaid on 2026-09-02.
      Read-only review: Codex proposed nothing and changed nothing.
      \## Critical
      - [modules/dev_junk.py:34](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/modules/dev_junk.py:34>) — VS Code Insiders paths are absent from the deny-list. With `HOME=/Users/alice`, a source-installed extension at `~/.vscode-insiders/extensions/acme.ext` containing a tracked `package.json` and `node_modules/loader.js` passes the Git check; unattended cleanup then trashes its dependencies and breaks the extension. Add `/.vscode-insiders/` and `/.vscode-server-insiders/` to `INSTALLED_SOFTWARE_MARKERS`, with tracked-checkout regression tests for both.
      \## Should-fix
      - [modules/dev_junk.py:173](</Volumes/Ext Data/VSC Projects/CC Dev/MacMaid/modules/dev_junk.py:173>) — the regex expects `pypy-…`, but PyPy uses tags such as `pypy39` without a hyphen ([Debian’s PyPy source](https://sources.debian.org/patches/pypy3/7.3.5%2Bdfsg-2%2Bdeb11u2/multiarch/)). Given tracked `mod.py` and `__pycache__/mod.pypy39.pyc`, `_source_of()` returns `mod.pypy39.py`, so the cache is never offered; one PyPy entry also blocks a mixed CPython/PyPy cache wholesale. Recognize `pypy\d+` tags and add tests for loose and `__pycache__` bytecode.
- [x] Interactive prompts default to Yes; dev_junk reads dev_scan_paths at import <!-- card:RHA8A2iF -->
      Found 2026-11-27 while running card 4J1ymHNX end to end. (1) Every interactive prompt defaults to Yes, so a stray Enter permanently empties old Trash or moves a reviewed file: consider default No, at least for Empty Trash and the per-file prompts. (2) modules/dev_junk.py:10 sets DEV_SCAN_PATHS from config at import, against the project rule that config is read inside scan().
- [x] config show/get: flag urgent above warn; ignore logs/ and state/ <!-- card:SnwKikx6 -->
      From the second review of 5e749d2. (1) config show and get do not flag a hand-edited storage_urgent_gb above storage_warn_gb, although ordinary writes are refused; mark it INVALID on the read path. (2) The untracked logs/ and state/ run files from the unattended runner are not in .gitignore; add /logs/ and /state/.
- [x] Low-storage warning: alert when the main disk drops below ~25 GB free <!-- card:XdqURsS7 -->
      Why: on 2026-11-05 the Data volume hit 99% full (4.7 GB free). macOS cache-purging (CacheDelete via RunningBoard) then kept force-quitting apps to reclaim space — RoboForm was killed 4 times in two days and relaunched locked each time, forcing re-login 5-7x a day. 72 GB was sitting in the Trash. disk_health.py already reads 'Volume Free Space' but only prints it, with no threshold, and only on the nightly run. Want: a threshold check (warn ~25 GB, urgent ~10 GB) run more often than nightly (e.g. hourly LaunchAgent or its own light check), alerting via mailgate --urgent / a macOS notification, naming the top space users (Trash size first). Also worth flagging: CacheDeleteAppContainerCaches terminations in the unified log are the early sign.
- [x] Run `python main.py` interactively end-to-end — needs a manual terminal <!-- card:4J1ymHNX -->
      (questionary uses the TTY directly, can't be driven headless).
- [x] config command: two review should-fixes <!-- card:eW3NcMyn -->
      From the review of 764a321 (config_cli.py): (1) check urgent <= warn on every change, not only when a threshold key changes, without blocking the way to clear a bad value; (2) refuse an empty path list or a ~name that does not resolve, since the scanners fall back to defaults or skip them.
- [x] Review server does not check the Host header or a per-session secret <!-- card:Sc0NjFwm -->
      From the Codex review of N1G8HJ0O (2026-11-27). /api/delete now reaches the Mail folder and phone backups. Cross-site JSON posts are blocked by the browser preflight, but DNS rebinding is not: check Host is localhost on every request, and add a per-session secret to delete, reveal and quit.
- [x] Trash scan says nothing is old when it could not check the Trash <!-- card:WNAOOKwI -->
      [claude] Found while fixing guPNotLn. If the Trash cannot be listed (the nightly job may not be allowed to read ~/.Trash, see 5YhIqK1s), or an entry has no recorded binned date or cannot be fully read, the Trash module counts it as 0 and says nothing has been in the Trash long enough. It should say how much could not be checked.
- [x] Trash emptying ages files by last-modified date, not by when they were binned <!-- card:guPNotLn -->
      cleaner.empty_trash() and modules/trash.reclaimable_size() compare the entry mtime with trash_retention_days. Moving to Trash keeps the old mtime, so a file last edited over 7 days ago can be permanently deleted by the next 02:00 run (large files, duplicates, Downloads files). Found by reading the code on 2026-11-27 while merging CleanUp. Not checked: whether the nightly job can list ~/.Trash at all. Fix so the 7 days count from when the item was binned, failing closed when that is unknown.
- [x] Extend `--review` + the email review link to other `risk=review` modules beyond <!-- card:N1G8HJ0O -->
      Large & Old Files and Duplicates, if any are added.
- [x] Add a `config` subcommand or interactive config editor. <!-- card:EyNoGPT2 -->
- [x] Test the Duplicates tab end-to-end in the browser UI: filter, sort, select, <!-- card:js35p4gA -->
      Move to Trash. UI confirmed loading (31,441 items) but the deletion flow has not
      been manually exercised.
- [x] Review UI and its email render at 11-12px <!-- card:5hkxisKU -->
      Next action: raise reviewer.py:150 (11px, the local self-review UI for flagged large files) and main.py:225 (12px, the Review Large Files email Fred receives).
      The global floor was raised 20px -> 24px on 2026-09-03 and Fred confirmed it 2026-09-04 for all projects. Both surfaces are read by him, so both are in scope. Only 2 files.
      Measure the rendered output with ~/.claude/skills/dashboard-ui/test_contrast_static.py (needs a venv with playwright), which now exits 1 on a breach rather than printing one. Worked example: CC Dev/Claude Usage 6f26511.
- [x] dev_junk: close the two residuals Codex left PARTIAL <!-- card:OpCUFRxY -->
      Follow-up to EEob21sz (fixed in 3f3ca9f). Neither is a live risk — both under-clean rather than over-clean — so they were deliberately left out of that diff rather than landing new surface unreviewed at the end of a long session.
      - Nested untracked activity is invisible. _worked_on_recently() stats the project directory and its immediate entries; work buried in a subdirectory shows up only if it is committed or is a tracked modification. Fix: run 'git status --porcelain -unormal' instead of -uno (git collapses an untracked directory to a single entry, so the listing stays small even where node_modules is not gitignored), stat each reported path and count only ones written inside the window. Needs the repo root to resolve status paths, which is one 'rev-parse --show-toplevel' per candidate.
      - That same rev-parse then lets the age and status answers be cached by REPOSITORY ROOT instead of by candidate parent — Codex's optional finding 7. On SiteBuilder that is 22 git calls instead of 40.
      - A project that is only ever RUN, never written to, can still be reclaimed. That is the feature as chosen (dormant-only automatic, over review-only) and is documented in CLAUDE.md — listed here so it is not rediscovered as a bug.
      Add a mutant for each in tools/redproof_dev_junk.py and keep the 14 that are there passing.
- [x] 1 module(s) changed today with no test touching them <!-- card:0KaAvcWu -->
      Changed today, and no test changed today imports or patches them:
      - tools/redproof_dev_junk.py
      a module counts as tested only if a test changed the same day imports it, names its path in a subprocess, is paired by name and directory with a test file (x_selftest.py beside x.py), or it declares a --selftest mode; this reports what nothing exercised today, not coverage
- [x] Skills check: bring macmaid-module home from the global skills <!-- card:Xpa2vzeU -->
      Global skills check (2026-09-14, owner answer 24A): this project's skills only apply here but sit in the global ~/.claude list and load in every project. During this project's skills-check batch, move them into this repo's .claude/ and re-key them in ~/.claude/skill-audit/descriptions.json. Method and state: ~/.claude/skill-audit/BATCHES.md
- [x] Raise self-viewed pages to the new 24px font floor <!-- card:z812i0dY -->
      Sweep this repo's own HTML/CSS for text below 24px and raise it, then re-measure in a real browser (computed style), not in the stylesheet.
      Why: the owner raised the global font floor from 20px to 24px on 2026-09-03. ~/.claude/skills/dashboard-ui/tokens.css, its test_contrast.py / test_contrast_static.py (MIN_PX now 24.0), md2pdf (MD2PDF_SCALE default 1.2) and the global `show` command have all moved. This repo carries its own copies of the old 20px numbers, so pages rendered from here are now below the floor.
      Scope check FIRST: client-facing pages are exempt — they follow the client's own design system and type scale. Only pages the owner personally reads (dashboards, reports, ops/status pages, internal tools, generated review pages) are in scope. If everything here is client-facing, close this card saying so.
      Blocks nothing, but every self-viewed page this repo renders is under-sized until done.
- [x] CLAUDE.md:42 names mac-maid-last-results.json, which is gone `🤖 rules drift` <!-- card:0SrpM8l6 -->
      - Next: open `MacMaid/CLAUDE.md` line 42 and either restore `mac-maid-last-results.json` or correct the reference.
      - Found by `rules-drift.py`: the token resolves to nothing in the repo, its git index, or by basename anywhere in the tree.
      - A stale path costs an agent a turn and fails silently.
- [x] CLAUDE.md:36 names mod.py, which is gone `🤖 rules drift` <!-- card:TzrxlwzC -->
      - Next: open `MacMaid/CLAUDE.md` line 36 and either restore `mod.py` or correct the reference.
      - Found by `rules-drift.py`: the token resolves to nothing in the repo, its git index, or by basename anywhere in the tree.
      - A stale path costs an agent a turn and fails silently.
- [x] CLAUDE.md:35 names package.json, which is gone `🤖 rules drift` <!-- card:zEC9M22e -->
      - Next: open `MacMaid/CLAUDE.md` line 35 and either restore `package.json` or correct the reference.
      - Found by `rules-drift.py`: the token resolves to nothing in the repo, its git index, or by basename anywhere in the tree.
      - A stale path costs an agent a turn and fails silently.
- [x] dev_junk trashes node_modules inside installed software (broke 6 VS Code extensions) <!-- card:mEU9eLek -->
      Root cause verified 2026-09-01. modules/dev_junk.py walks dev_scan_paths (~/ and /Volumes/Ext Data) and trashes EVERY node_modules it finds, with no exclusion for installed software. On 2026-08-30 16:14 it stripped node_modules from 5 VS Code extensions in ~/.vscode/extensions, which is why Code Spell Checker threw 'Configuration Loader Error: Failed to resolve @cspell/dict-en-gb/cspell-ext.json'. Also truncated: esbenp.prettier-vscode, peakchen90.open-html-in-browser, yzane.markdown-pdf, streetsidesoftware.code-spell-checker. All 5 restored by hand from marketplace VSIXs; they will break again on the next run. Today's scan ALSO lists 10 node_modules under hidden ~ dirs including ~/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules and ~/.codex/plugins/... - i.e. it can break the Codex CLI runtime that gates every commit on this machine. Fix: add an exclusion list to dev_junk (skip any node_modules whose path contains an installed-software root: ~/.vscode, ~/.vscode-insiders, ~/.cursor, ~/.codex, ~/.cache, ~/.npm/_npx, ~/Library/Application Support, /Applications), or better, only offer a node_modules whose parent dir contains a package.json AND sits under a git working tree. Regression test: assert a node_modules planted under ~/.vscode/extensions/<x>/ is NOT returned by dev_junk.scan().
      UPDATE 2026-09-01: a SIXTH extension was also stripped and was nearly missed. The first audit used `du`, which counts disk blocks, and scored ms-python.python at 97%; measured as the sum of file sizes it is 76%, with 7.4 MB of node_modules gone from out/client/node_modules — nested, so a top-level check misses it too. All six restored; see CC Dev/General/vscode-extensions-stripped-by-macmaid.md.
- [x] Nightly sweep trashes node_modules in live dev projects <!-- card:EEob21sz -->
      Next action: exclude a node_modules whose sibling package.json is TRACKED by git, or add a per-project opt-out file, then re-run the dev_junk scan and confirm the DeckForge path is no longer offered.
      - Measured 2026-09-08 from the Google Slides (DeckForge) project: remotion/node_modules has now vanished EIGHT times. The test suite came back 27 failed / 13 errors, every failure tracing to "Remotion is not installed".
      - Mechanism: com.macmaid.nightly (02:00, deferred to wake) runs main.py --unattended. config.json dev_scan_paths includes /Volumes/Ext Data; modules/dev_junk.py TARGET_DIRS includes node_modules and returns risk=safe / action=trash; main.py unattended_mode auto-cleans every safe item with no confirmation.
      - The 2026-09-01 guard is what SELECTS DeckForge rather than sparing it: it keeps a node_modules only when git tracks a manifest beside it, and remotion/package.json is tracked. Genuine live projects are exactly the case being deleted.
      - It goes to the volume Trash (/Volumes/Ext Data/.Trashes/501/, not ~/.Trash), and MacMaid empty_trash permanently deletes past trash_retention_days=7 -- which is why earlier searches of ~/.Trash found nothing.
      - Cost each time: npm ci, plus a red suite that reads like a code regression until someone checks.
      - It will happen again at the next nightly run until this lands.
      Raised by the Google Slides /dispatch cycle 2026-09-08. Cross-project: logged here, not built there.
- [x] Nightly cache sweep bins ~/Library/Caches/ms-playwright and breaks every Playwright test run <!-- card:fuPhf3U8 -->
      Found 2026-09-14 from seomachine. modules/caches.py trashes EVERY entry under ~/Library/Caches with no protected list, and com.macmaid.nightly runs it at 02:00. ms-playwright (the Playwright browser binaries, ~500 MB) has landed in ~/.Trash 18 times ('ms-playwright HH-MM-SS-mmm' copies; mac-maid.log also lists ms-playwright-mcp). Each time, seomachine's suite loses ~150 browser tests (128 failed + 25 errors + 26 skipped on 2026-09-14) and its commit gate refuses the run, so night runs cannot land work. It is not junk: reinstalling means a fresh download and a Playwright-version match.
      Next action: add a protected-names list to the caches module (at minimum ms-playwright and ms-playwright-mcp; worth checking the same for other tool-owned caches such as pip wheels in use, uv, Homebrew downloads), skip those entries in _scan_cache_dir, and add a test that a protected entry is never offered. Verify: after the next 02:00 run, ~/Library/Caches/ms-playwright still exists.
      Restored by hand 2026-09-14 from the newest Trash copy (chromium-1208).
