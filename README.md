# Mac Maid

A macOS maintenance tool that scans for junk, reports what it finds, and cleans up safely.

## Features

- **14 scan modules**: caches, logs, trash, large/old files, duplicates, dev junk, browser caches, mail store, login items, disk health, memory pressure, thermal/CPU, iOS backups, Xcode simulators
- **Interactive mode**: review each category and choose what to clean
- **Unattended mode**: auto-clean safe items and email a report
- **Scheduler**: install a nightly LaunchAgent with one command
- **Run history**: log of every unattended run

## Requirements

- macOS (Apple Silicon recommended for thermal module)
- Python 3.11+

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Interactive scan

```bash
python main.py
```

Scans all enabled modules, displays results, then walks you through each category asking what to clean.

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

### View run history

```bash
python main.py --history
```

Shows the last 10 unattended run records (date, items cleaned, bytes freed).

### Permanent delete

```bash
python main.py --permanent
```

Deletes files immediately instead of moving to Trash. Use with care.

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

`dev_junk_dormant_days` is how long a project must have gone without a commit before its
`node_modules` counts as junk. A project is also spared while anything local says it is in
use — the dependencies were installed recently, a tracked file beside them was edited, or
the repository has uncommitted work. Lower it to reclaim more; values below 1 are ignored.

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
