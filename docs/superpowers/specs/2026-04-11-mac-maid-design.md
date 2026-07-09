# Mac Maid — Design Spec
**Date:** 2026-04-11  
**Status:** Approved for implementation

---

## Overview

Mac Maid is a personal macOS maintenance CLI tool that scans the system, surfaces actionable findings, and cleans up junk files safely — with full reversibility via Trash. It runs on demand or on a nightly schedule, emailing a summary report in the morning.

Built for personal weekly use now; designed to be upgraded to a GUI app later without rewriting the core engine.

---

## Goals

- Replace CleanMyMac for personal Mac maintenance
- Scan first, suggest actions, require confirmation before any changes
- Never permanently delete anything without explicit user intent
- Run fully unattended overnight and deliver a morning email report
- Monitor M4 thermal health and flag performance throttling

---

## Non-Goals

- Not a real-time monitor (that's Stats/System Status Monitor)
- Not a multi-user or networked tool
- No plugin system or public API (personal tool only)
- No GUI in v1

---

## Architecture

### Principle: Engine / Presenter separation

Every module returns structured data. It never prints anything directly. The presenter (`reporter.py`) handles all terminal output. This means a future GUI replaces `reporter.py` only — the engine is untouched.

### Project structure

```
MacMaid/
├── main.py              ← entry point, CLI args, orchestration
├── config.json          ← user-editable settings and thresholds
├── modules/
│   ├── caches.py
│   ├── logs.py
│   ├── trash.py
│   ├── large_files.py
│   ├── duplicates.py
│   ├── dev_junk.py
│   ├── browsers.py
│   ├── mail.py
│   ├── login_items.py
│   ├── disk_health.py
│   ├── memory.py
│   └── thermal.py
├── reporter.py          ← all Rich formatting, tables, panels
├── cleaner.py           ← executes confirmed deletions via send2trash
├── scheduler.py         ← installs/removes macOS LaunchAgent
└── emailer.py           ← wraps ~/.claude/utils/send_email.py
```

### Module result schema

Every module returns a dict:
```python
{
    "category": str,          # display name
    "risk": str,              # "safe" | "review" | "inform-only"
    "items": [                # list of findings
        {
            "path": str,
            "size_bytes": int,
            "label": str,     # human-readable description
            "meta": dict      # optional extra data (last opened, duplicate of, etc.)
        }
    ],
    "total_size_bytes": int,
    "suggestion": str,        # one-line recommendation shown to user
    "action": str             # "trash" | "empty-trash" | "none"
}
```

---

## Run Flow

### Interactive mode (default)

```
1. Print banner
2. "Scanning your Mac..." — Rich progress bar, all 12 modules run in parallel where safe
3. Results screen — categorised panels, size per category, risk level indicator
4. Per-category confirmation prompts (questionary):
     safe items:   "Clean [category]? Saves X GB [y/n/details]"
     review items: "Review [category] (X items)? [y/n]" → shows each item individually
     inform-only:  no prompt, just displayed
5. Cleaner executes confirmed actions — tick per item as it goes
6. Summary: X GB freed, Y items removed, Z skipped, Trash reminder
```

### Unattended/scheduled mode (--unattended flag)

- Runs all modules
- Auto-confirms all `safe` items
- Skips all `review` items (too risky without human eyes)
- Generates a Rich-formatted text report
- Emails report to kmmsubs@gmail.com via ~/.claude/utils/send_email.py
- Subject: "Mac Maid Report — [date] — X GB freed"

### Scheduling

```bash
python main.py --schedule "02:00"    # install LaunchAgent, run nightly at 2am
python main.py --unschedule          # remove LaunchAgent
python main.py --schedule-status     # show current schedule
```

Installs a plist to `~/Library/LaunchAgents/com.macmaid.nightly.plist`.

---

## Modules

### Risk levels
- **safe** — auto-suggest deletion; confirmed in bulk
- **review** — shown individually; user decides per-item
- **inform-only** — never deleted; displayed as health info only

---

### 1. Caches `safe`
- Paths: `~/Library/Caches`, `/Library/Caches`
- Groups by app name, shows size per app
- Action: move all to Trash via send2trash
- Skips: locked files, anything that errors silently

### 2. Logs `safe`
- Paths: `~/Library/Logs`, `/private/var/log`
- Targets files older than 7 days (configurable)
- Action: move to Trash

### 3. Trash `safe` (special)
- Reports current Trash size
- Action: `empty` — permanent delete, requires explicit "yes I want to empty the Trash" confirm
- This is the only module that permanently deletes (it's already in the bin)

### 4. Large & Old Files `review`
- Scans: `~/Downloads`, `~/Desktop`, `~/Documents` (configurable)
- Flags: files over 500MB OR untouched for 180+ days (both configurable)
- Shows each file: name, size, last opened date
- Action: user picks individually which to move to Trash

### 5. Duplicates `review`
- Scans same paths as Large & Old Files
- Method: MD5 hash comparison
- Groups duplicates, keeps newest, suggests moving older copies to Trash
- Shows each group so user can verify before confirming

### 6. Dev Junk `safe`
- Targets:
  - `node_modules/` — scans `~/` and `/Volumes/Ext Data`
  - `__pycache__/` and `.pyc` files
  - `~/Library/Developer/Xcode/DerivedData`
  - `~/Library/Caches/pip`
  - npm cache (`~/.npm/_cacache`)
  - Composer cache (`~/.composer/cache`)
  - `.DS_Store` files (permanent delete — zero value, tiny)
- Action: move to Trash (except .DS_Store → permanent)

### 7. Browsers `safe`
- Cache directories only — never history, bookmarks, passwords
  - Safari: `~/Library/Caches/com.apple.Safari`
  - Chrome: `~/Library/Caches/Google/Chrome`
  - Firefox: `~/Library/Caches/Firefox`
- Action: move to Trash

### 8. Mail `review`
- Scans `~/Library/Mail` attachment cache
- Marked review: some users rely on cached attachments for offline access
- Action: move to Trash if confirmed

### 9. Login Items `inform-only`
- Lists all startup items via `osascript`
- Flags any whose path no longer exists (dead entries)
- No action — user acts manually via System Settings if desired
- Displayed as informational panel only

### 10. Disk Health `inform-only`
- `diskutil info /` — capacity, free space, used %
- `smartctl` — SMART status if Homebrew smartmontools installed; gracefully skipped if not
- Output: simple status `OK / Warning / Unknown`
- No action

### 11. Memory `inform-only`
- Parses `vm_stat` output
- Reports: free, active, wired, compressed memory
- Pressure level: `Normal / Warning / Critical`
- No action

### 12. Thermal `inform-only`
- Runs `sudo powermetrics --samplers smc,cpu_power -n 1 --output-format json`
- Requires sudoers rule (one-time setup, guided on first run if missing):
  `fred ALL=(ALL) NOPASSWD: /usr/bin/powermetrics`
- Reports:
  - Efficiency core temp
  - Performance core temp  
  - GPU temperature
  - Current power draw (W)
  - **Thermal pressure level** (Nominal / Light / Moderate / Heavy / Critical)
  - **Throttling detected** (Yes/No)
- If pressure is Moderate or above: surfaces top CPU-consuming processes and simple suggestions
- No action

---

## Deletion Safety

| Scenario | Behaviour |
|---|---|
| Default cleaning | `send2trash` — files go to macOS Trash, fully reversible |
| `--permanent` flag | Bypasses Trash, permanent delete — for confident use |
| Trash module | Always permanent (already in Trash), requires explicit confirm |
| `.DS_Store` files | Always permanent — no value, tiny |
| Errors during delete | Logged, skipped — never crashes |

Summary line always shown after cleaning: *"X files moved to Trash. Review before emptying."*

---

## Configuration (config.json)

```json
{
  "large_file_threshold_mb": 500,
  "old_file_days": 180,
  "log_retention_days": 7,
  "scan_paths": ["~/Downloads", "~/Desktop", "~/Documents"],
  "dev_scan_paths": ["~/", "/Volumes/Ext Data"],
  "email_report_to": "kmmsubs@gmail.com",
  "modules": {
    "caches": true,
    "logs": true,
    "trash": true,
    "large_files": true,
    "duplicates": true,
    "dev_junk": true,
    "browsers": true,
    "mail": true,
    "login_items": true,
    "disk_health": true,
    "memory": true,
    "thermal": true
  },
  "permanent_delete": false
}
```

---

## Dependencies

```
rich          # terminal formatting, progress bars, tables, panels
questionary   # interactive prompts, checkboxes, confirms
send2trash    # cross-platform Trash integration
```

All installable via `pip install rich questionary send2trash`.

No external APIs. No network calls. All data is local.

---

## CLI Interface

```bash
python main.py                    # interactive full scan
python main.py --unattended       # silent clean + email report
python main.py --modules caches logs dev_junk   # run specific modules only
python main.py --schedule "02:00" # install nightly LaunchAgent
python main.py --unschedule       # remove LaunchAgent
python main.py --schedule-status  # show schedule info
python main.py --permanent        # skip Trash, delete directly
python main.py --no-email         # unattended without emailing
```

---

## One-time Setup

1. `pip install rich questionary send2trash`
2. Add sudoers rule for powermetrics (guided prompt on first run if missing)
3. Optionally: `python main.py --schedule "02:00"` for nightly automation

---

## Future (v2 — not in scope now)

- Swift/Electron GUI wrapper calling the Python engine via subprocess
- Per-app cache exclusion list
- SMART data without requiring smartmontools (native IOKit)
- Fan speed reading (requires SMC access)
