# Mac Maid

A macOS maintenance tool that scans for junk, reports what it finds, and cleans up safely.

## Features

- **15 scan modules**: caches, logs, trash, Downloads auto-clean (off by default), large/old files, duplicates, dev junk, browser caches, mail store, login items, disk health, memory pressure, thermal/CPU, iOS backups, Xcode simulators
- **Browser app**: `python main.py` opens a page that scans, shows every category and cleans what you choose
- **Terminal mode**: the same flow as questions in the terminal (`--terminal`)
- **Unattended mode**: auto-clean safe items and email a report
- **Scheduler**: install a nightly LaunchAgent with one command
- **Run history**: log of every unattended run

## Requirements

- macOS (Apple Silicon recommended for thermal module)
- Python 3.11+
- Google Chrome (the test suite renders the review page and email in it)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Scan and clean in the browser

```bash
python main.py
```

Opens MacMaid in your browser and starts a scan, showing each category as it finishes. The Summary tab lists every category with its size; each category with results has its own tab. Caches, logs and the review categories (large files, duplicates, mail, iOS backups) let you tick items and move them to the Trash. The Trash tab empties entries that have been in the Trash longer than `trash_retention_days`, after its own confirmation. Information categories (disk health, memory, thermal, login items) have nothing to delete. **Scan again** reruns the scan. Apart from emptying old Trash, the browser never deletes permanently. Press Ctrl-C in the terminal, or Done in the page, to stop it.

### Scan and clean in the terminal

```bash
python main.py --terminal
```

Scans all enabled modules, displays results, then walks you through each category asking what to clean. Pressing Enter takes the capital-letter answer: it is No for emptying the Trash, for each reviewed file and for every deletion under `--permanent`.

### Unattended scan

```bash
python main.py --unattended
```

Automatically cleans all `safe`-risk items and emails a report (configure `email_report_to` in `config.json`).

### Dry run (no deletion)

```bash
python main.py --unattended --dry-run
```

Runs the full scan and generates a report without deleting anything. Useful for previewing what unattended mode would do.

### Run specific modules

```bash
python main.py --modules caches logs trash
```

### Schedule nightly runs

```bash
# Install LaunchAgent at 02:00
python main.py --schedule 02:00

# Check schedule status
python main.py --schedule-status

# Remove schedule
python main.py --unschedule
```

Trash entries are permanently deleted once they have been in the Trash for
`trash_retention_days` (7), counted from when they were binned, not when they were last edited.
Anything written to after that (including deep inside a folder) restarts the count. Hard-linked
files, and entries on a volume that does not record the binned date, are kept. The report says
what it could not check (a Trash folder it could not open, or items whose age it could not tell)
rather than counting it as nothing old.

`--schedule` also installs an hourly low-storage check (`com.macmaid.storage`), and
`--unschedule` removes both. Run it by hand with:

```bash
python main.py --storage-check
```

Below `storage_warn_gb` free on the main disk it emails you and shows a notification, naming
the Trash first and then the largest folders; below `storage_urgent_gb` the email is sent as
urgent. It alerts once per level, again sooner only if things get worse, and repeats after
`storage_realert_hours`. State lives in `~/Library/Logs/mac-maid-storage-state.json`.

The scheduled check cannot read the Trash, Mail or iPhone backups unless the Python it runs under
has Full Disk Access (System Settings > Privacy & Security); the email names that Python when it
was blocked. Granting it is a security choice: every script run by that Python gets the same access. A folder it could only partly read shows as "at least N GB". The email also says how
many local Time Machine snapshots there are, since they can hold on to the space of deleted files.

### View run history

```bash
python main.py --history
```

Shows the last 10 unattended run records (date, items cleaned, bytes freed).

### Permanent delete

```bash
python main.py --permanent
```

Deletes files immediately instead of moving to Trash. Use with care. This always runs in the terminal, since the browser only moves to the Trash.

## Configuration

Copy or create `config.json` in the project root. All keys are optional — defaults are shown below.

```json
{
  "large_file_threshold_mb": 500,
  "old_file_days": 180,
  "log_retention_days": 7,
  "scan_paths": ["~/Downloads", "~/Desktop", "~/Documents"],
  "dev_scan_paths": ["~/", "/Volumes/Ext Data"],
  "dev_junk_dormant_days": 180,
  "email_report_to": "you@example.com",
  "permanent_delete": false,
  "storage_warn_gb": 25,
  "storage_urgent_gb": 10,
  "storage_realert_hours": 24,
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
  }
}
```

Set any module to `false` to skip it.

Settings can also be viewed and changed without editing the file:

```bash
python main.py config                               # every setting, defaults marked
python main.py config get old_file_days
python main.py config set old_file_days 90
python main.py config set modules.thermal false
python main.py config set scan_paths ~/Downloads ~/Desktop
python main.py config unset old_file_days           # back to the default
```

Unknown settings and values that make no sense are refused, and a damaged `config.json`
is left untouched. Changes apply from the next run, including the scheduled one.

Path settings need at least one path. `storage_urgent_gb` may not be above
`storage_warn_gb` — if a hand edit left it that way, fix it before changing anything else
(correcting another invalid value is still allowed). `config` and `config get` mark both
levels `INVALID` while they are that way round.

`dev_junk_dormant_days` is how long a project must have gone without a commit before its
`node_modules` counts as junk. A project is also spared while anything local says it is in
use — the dependencies were installed recently, a file beside them was edited, or the
repository has uncommitted changes or recently written untracked files. Lower it to reclaim more; values below 1 are ignored.

## Thermal module (sudo required)

The thermal module uses `powermetrics` which requires passwordless sudo. To enable:

```bash
sudo visudo
```

Add this line (replace `fred` with your username):

```
fred ALL=(ALL) NOPASSWD: /usr/bin/powermetrics
```

If not configured, the thermal module is skipped with a clear message.

## Running tests

```bash
source .venv/bin/activate
python -m pytest tests/
```
