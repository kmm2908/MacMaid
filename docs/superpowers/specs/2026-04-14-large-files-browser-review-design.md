# Large Files Browser Review — Design Spec
**Date:** 2026-04-14
**Status:** Approved

## Problem

The unattended daily scan reports large/old files (potentially tens of thousands, many GB) but provides no way to act on them after the fact. The interactive mode's per-item confirm loop is impractical at scale. Users need a way to browse, filter, and selectively delete these files after receiving the email report.

## Solution

A browser-based review UI triggered by a clickable `macmaid://review` link in the email report. Clicking the link starts a local Flask server and opens the browser to a sortable, filterable table with checkboxes and bulk delete.

---

## Data Flow

```
Unattended scan (2am)
  → saves full scan results to ~/Library/Logs/mac-maid-last-results.json
  → sends email with "Review large files →" link (macmaid://review)

User clicks link in Mail.app
  → macOS routes macmaid:// to ~/.local/share/MacMaid.app bundle
  → app bundle runs: python main.py --review
  → Flask server starts on a random free port
  → browser opens to http://localhost:PORT
  → user filters/sorts/selects files, clicks "Move to Trash"
  → Flask calls cleaner.clean_items() with selected paths
  → server shuts down when user closes tab or clicks Done
```

---

## Components

### 1. Results Persistence (`main.py`)
- After every unattended scan, save the full `results` list to `~/Library/Logs/mac-maid-last-results.json`
- Overwrites on each run (only the latest scan is needed)

### 2. Email Link (`emailer.py`)
- When the email report includes a `large_files` result with items, append a `macmaid://review` link to the email body
- Only shown when there are actionable items (risk = "review")

### 3. URL Scheme Handler (`url_handler.py` — new)
- Creates a minimal macOS app bundle at `~/.local/share/MacMaid.app`
- `Info.plist` registers the `macmaid://` URL scheme with Launch Services
- The bundle's executable shell script calls `python main.py --review`
- Registers the bundle with `lsregister` so macOS recognises the scheme
- `setup()` is idempotent — safe to call on every `--schedule` install

### 4. Scheduler Integration (`scheduler.py`)
- Calls `url_handler.setup()` after installing the LaunchAgent
- Ensures the URL scheme is registered whenever the user runs `--schedule`

### 5. Review Server (`reviewer.py` — new)
Flask server with three endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve the review HTML page |
| `/api/files` | GET | Return large_files items as JSON |
| `/api/delete` | POST | Accept list of paths, call `cleaner.clean_items()`, return result |
| `/api/reveal` | POST | Call `open -R <path>` to reveal file in Finder |

- Port is chosen dynamically (bind to port 0, let OS assign)
- Server starts in a background thread; main thread opens the browser
- Graceful shutdown endpoint (`/api/quit`) or auto-shutdown after 30-minute idle

### 6. Review UI (embedded in `reviewer.py`)
Single self-contained HTML page served inline. Vanilla JS, no frameworks.

**Table columns:** Checkbox / Name / Full Path / Size / Age (days) / Last Modified

**Controls:**
- Live filter box — searches across Name and Full Path
- Sortable column headers (click to sort asc/desc)
- Select All / Deselect All checkbox
- **"Move to Trash" button** — shows count + total size of selected files, requires click to confirm, then POSTs to `/api/delete`
- **"Reveal in Finder" icon** per row — POSTs path to `/api/reveal`

**After deletion:**
- Deleted rows are removed from the table
- A summary bar shows total space freed in the session
- Failed deletions shown in red with the error message

### 7. `--review` Flag (`main.py`)
- Loads `~/Library/Logs/mac-maid-last-results.json`
- Passes large_files items to `reviewer.start()`
- If no saved results: exits with a friendly message directing user to run a scan first

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| No saved results JSON | Browser shows "No scan data — run MacMaid first" message |
| File deleted between scan and review | `cleaner.clean_items()` handles `FileNotFoundError`; UI shows per-file errors in red |
| Port conflict | Use `socket` port 0 to get a free port from the OS |
| URL scheme not registered | `--schedule` re-registers on every install; first-time users must run `--schedule` |
| Flask not installed | Add `flask` to `pyproject.toml` dependencies |

---

## Dependencies

- **New:** `flask` (add to `pyproject.toml`)
- **No other new dependencies** — URL handler uses shell script + `lsregister` (macOS built-in)

---

## Files Changed

| File | Change |
|------|--------|
| `main.py` | Add `--review` flag; save results JSON after unattended run |
| `emailer.py` | Append `macmaid://review` link when large_files has items |
| `scheduler.py` | Call `url_handler.setup()` after LaunchAgent install |
| `reviewer.py` | **New** — Flask server + embedded HTML/JS review UI |
| `url_handler.py` | **New** — macOS app bundle creation + URL scheme registration |
| `pyproject.toml` | Add `flask` dependency |

---

## Verification

1. Run `python main.py --schedule` — confirm `MacMaid.app` created at `~/.local/share/MacMaid.app` and `macmaid://` scheme is registered (`lsregister -dump | grep macmaid`)
2. Run `python main.py --unattended --dry-run` — confirm `mac-maid-last-results.json` is written and email contains `macmaid://review` link
3. Click the link in Mail.app — confirm browser opens to `http://localhost:<PORT>`
4. In the UI: filter by a directory name, sort by size, select a few files, click Move to Trash — confirm files move to Trash and rows disappear
5. Click Reveal in Finder on a row — confirm Finder opens with the file highlighted
6. Run `python main.py --review` with no saved results — confirm friendly error message
