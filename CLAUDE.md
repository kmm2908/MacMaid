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
- **`dev_junk` fails closed** — for the artefacts it *walks* (`TARGET_DIRS` + `TARGET_EXTS`). The three static paths `scan()` appends by name (Xcode DerivedData, the pip cache, `~/.npm/_cacache`) are unconditional and bypass all of it, `is_removable()` included; they are vendor caches at fixed locations, so that is deliberate. For everything walked, the artefact is offered only when git tracks matching evidence **directly in its parent directory** — `package.json` for `node_modules`; a `.py` or a `PY_PROJECT_FILES` entry for `__pycache__`/`.mypy_cache`/`.pytest_cache`/`.pyc` (a frozen app ships bytecode with the source stripped, so a tracked README proves nothing) — and that entry must **exist on disk**, since `ls-files` reports the index, not the working tree. The resolved path must also be under no `INSTALLED_SOFTWARE_MARKERS` segment, no `HOME_INSTALL_ROOTS` subtree, and inside no `BUNDLE_SUFFIXES` bundle (`.app`, `.framework`, …). An ancestor `.git` is deliberately NOT enough: installed software lives untracked inside checkouts (`~/.claude/plugins/cache/…`, `.venv/…/site-packages/…`), and a `.git` at a broad scan root would otherwise bless everything under it.
  - For bytecode the evidence must be **its own** source: `mod.cpython-312.pyc` needs a tracked `mod.py`, and a `__pycache__` is offered only when *every* `.pyc` inside it maps to one — the cleaner removes the directory wholesale, so one orphan condemns it.
  - **Accepted trade-offs.** A genuine project under `~/bin`, `~/opt`, `~/go`, `~/.config` or `~/Library` is never offered (pinned by a test). A tool installed by `git clone` + `npm install` into a location none of those lists names still is — the known residual, not covered. Anything git cannot answer for — no binary, a hang, an operational failure, an exhausted `GIT_SCAN_BUDGET_SECONDS` — is declined and counted into the result's suggestion, so an incomplete scan does not read as a clean machine. `GIT_CEILING_DIRECTORIES` is honoured because it *restricts* discovery; stripped are the variables that redirect git to another index, change what `:(glob)*` means, or widen discovery (`GIT_DISCOVERY_ACROSS_FILESYSTEM`), and `LC_ALL`/`LANG` are pinned to `C` so the non-repository answer is not read in a translation
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


## Autonomy
Exhaust every automation path (API, CLI, MCP, scripted browser) before handing a task back. **Full rule:** `~/.claude/rules/common/autonomy.md`.



## Subagent Offloading

Dispatch to a subagent (not inline) when any trigger fires: reading >3 files for one question, open-ended search, multi-step research, any task >2 min, batch operations, or verifying external-system claims. Use `run_in_background: true` for long-running tasks. **Sonnet is the floor for all subagents — never Haiku.** **Full rule + exceptions:** `~/.claude/rules/common/subagent-offloading.md`.
