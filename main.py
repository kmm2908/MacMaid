#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import questionary
from rich.console import Console

import config as cfg
import reporter
import cleaner as cleaner_mod
import emailer
import scheduler
import history
import reviewer

from modules import (
    caches, logs, trash, large_files, duplicates,
    dev_junk, browsers, mail, login_items, disk_health, memory, thermal,
    ios_backups, xcode_sims,
)

console = Console()

RESULTS_PATH = Path.home() / "Library" / "Logs" / "mac-maid-last-results.json"


def save_results(results: list[dict]) -> None:
    RESULTS_PATH.write_text(json.dumps(results))


MODULES = {
    "caches": caches.scan,
    "logs": logs.scan,
    "trash": trash.scan,
    "large_files": large_files.scan,
    "duplicates": duplicates.scan,
    "dev_junk": dev_junk.scan,
    "browsers": browsers.scan,
    "mail": mail.scan,
    "login_items": login_items.scan,
    "disk_health": disk_health.scan,
    "memory": memory.scan,
    "thermal": thermal.scan,
    "ios_backups": ios_backups.scan,
    "xcode_sims": xcode_sims.scan,
}


def run_scan(enabled_modules: list[str]) -> list[dict]:
    results = []
    with reporter.make_progress() as progress:
        task = progress.add_task("Scanning...", total=len(enabled_modules))
        for name in enabled_modules:
            progress.update(task, description=f"Scanning {name}...")
            scan_fn = MODULES.get(name)
            if not scan_fn:
                progress.advance(task)
                continue
            try:
                result = scan_fn()
            except Exception as e:
                result = {
                    "category": name, "risk": "safe", "items": [],
                    "total_size_bytes": 0,
                    "suggestion": f"Error: {e}", "action": "none"
                }
            results.append(result)
            progress.advance(task)
    return results


def interactive_mode(results: list[dict], permanent: bool) -> cleaner_mod.CleanResult:
    total_result = cleaner_mod.CleanResult()

    for r in results:
        if r["risk"] == "inform-only" or not r["items"]:
            continue

        if r["risk"] == "safe":
            size = reporter.format_size(r["total_size_bytes"])
            confirm = questionary.confirm(
                f"Clean {r['category']}? ({size})"
            ).ask()
            if confirm:
                cr = cleaner_mod.clean_items(r["items"], permanent=permanent)
                total_result.moved += cr.moved
                total_result.errors += cr.errors
                total_result.bytes_freed += cr.bytes_freed

        elif r["risk"] == "review":
            show = questionary.confirm(
                f"Review {r['category']} ({len(r['items'])} items)?"
            ).ask()
            if not show:
                continue
            to_clean = []
            for item in r["items"]:
                reporter.print_item_detail(item)
                keep = questionary.confirm(f"  Move to Trash?").ask()
                if keep:
                    to_clean.append(item)
            if to_clean:
                cr = cleaner_mod.clean_items(to_clean, permanent=permanent)
                total_result.moved += cr.moved
                total_result.errors += cr.errors
                total_result.bytes_freed += cr.bytes_freed

    return total_result


def _start_review_server() -> None:
    """Stop any running review server, launch a fresh one, and wait until it's ready."""
    try:
        urllib.request.urlopen(
            f"http://localhost:{reviewer.REVIEW_PORT}/api/quit", data=b"{}", timeout=1
        )
        time.sleep(0.5)
    except Exception:
        pass
    # Force-kill anything still holding the port
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{reviewer.REVIEW_PORT}"],
            capture_output=True, text=True,
        )
        for pid in result.stdout.split():
            subprocess.run(["kill", "-9", pid], capture_output=True)
        if result.stdout.strip():
            time.sleep(0.5)
    except Exception:
        pass
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--serve"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to 10s for the server to be ready before emailing the link
    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://localhost:{reviewer.REVIEW_PORT}/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.5)


def unattended_mode(results: list[dict], permanent: bool, to_email: str, no_email: bool, dry_run: bool = False) -> None:
    items_to_clean = [
        item
        for r in results
        if r["risk"] == "safe" and r["action"] != "none"
        for item in r["items"]
    ]
    if dry_run:
        clean_result = cleaner_mod.CleanResult()
    else:
        clean_result = cleaner_mod.clean_items(items_to_clean, permanent=permanent)
    report_text = reporter.print_unattended_report(results, clean_result, dry_run=dry_run)

    if not dry_run:
        save_results(results)
    history.record(clean_result, dry_run=dry_run)

    if not no_email and to_email:
        has_reviewable = bool(_load_review_categories(results))
        html_body = None
        if has_reviewable:
            _start_review_server()
            review_url = f"http://localhost:{reviewer.REVIEW_PORT}"
            report_text += f"\n\n---\nReview large files: {review_url}"
            escaped = report_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_body = (
                f'<pre style="font-family:monospace;white-space:pre-wrap">{escaped}</pre>'
                f'<hr style="margin:20px 0">'
                f'<p><a href="{review_url}" style="display:inline-block;padding:12px 24px;background:#2980b9;color:#ffffff;'
                f'text-decoration:none;border-radius:6px;font-family:sans-serif;font-size:15px;font-weight:bold">'
                f'&#x1f9f9; Review Large Files &rarr;</a></p>'
                f'<p style="color:#999;font-size:12px;font-family:sans-serif">Opens on this Mac while MacMaid review server is running.</p>'
            )
        prefix = "[DRY RUN] " if dry_run else ""
        subject = f"{prefix}Mac Maid Report — {date.today()} — {reporter.format_size(clean_result.bytes_freed)} freed"
        emailer.send_report(subject, report_text, to_email, html_body=html_body)


_REVIEW_CATEGORIES = ("Large & Old Files", "Duplicates")


def _load_review_categories(results: list[dict]) -> dict[str, list[dict]]:
    """Extract reviewable categories (with items) from scan results."""
    cats = {}
    for name in _REVIEW_CATEGORIES:
        r = next((r for r in results if r.get("category") == name and r.get("items")), None)
        if r:
            cats[name] = r["items"]
    return cats


def main() -> None:
    parser = argparse.ArgumentParser(description="Mac Maid — macOS maintenance tool")
    parser.add_argument("--unattended", action="store_true", help="Run silently and email report")
    parser.add_argument("--modules", nargs="+", help="Run specific modules only")
    parser.add_argument("--permanent", action="store_true", help="Delete permanently instead of Trash")
    parser.add_argument("--no-email", action="store_true", help="Skip email in unattended mode")
    parser.add_argument("--dry-run", action="store_true", help="Scan and report without deleting anything")
    parser.add_argument("--schedule", metavar="HH:MM", help="Install nightly LaunchAgent")
    parser.add_argument("--unschedule", action="store_true", help="Remove LaunchAgent")
    parser.add_argument("--schedule-status", action="store_true", help="Show schedule status")
    parser.add_argument("--history", action="store_true", help="Show last 10 run history entries")
    parser.add_argument("--review", action="store_true", help="Open browser review UI for last scan results")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.schedule:
        ok = scheduler.install(args.schedule)
        console.print(f"[green]Scheduled at {args.schedule}[/green]" if ok else "[red]Schedule failed[/red]")
        return

    if args.unschedule:
        ok = scheduler.uninstall()
        console.print("[green]Unscheduled[/green]" if ok else "[yellow]No schedule found[/yellow]")
        return

    if args.schedule_status:
        console.print(scheduler.status())
        return

    if args.history:
        console.print(history.format_history())
        return

    if args.serve:
        if not RESULTS_PATH.exists():
            sys.exit(1)
        results = json.loads(RESULTS_PATH.read_text())
        cats = _load_review_categories(results)
        if not cats:
            sys.exit(0)
        reviewer.serve(cats)
        sys.exit(0)

    if args.review:
        if not RESULTS_PATH.exists():
            console.print("[red]No scan data found. Run MacMaid with --unattended first.[/red]")
            sys.exit(1)
        results = json.loads(RESULTS_PATH.read_text())
        cats = _load_review_categories(results)
        if not cats:
            console.print("[yellow]No large files found in last scan.[/yellow]")
            sys.exit(0)
        reviewer.start(cats)
        sys.exit(0)

    reporter.print_banner()

    enabled = args.modules or [
        name for name in MODULES if cfg.module_enabled(name)
    ]

    results = run_scan(enabled)
    reporter.print_results(results)

    permanent = args.permanent or cfg.get("permanent_delete") or False

    if args.unattended:
        to_email = cfg.get("email_report_to") or ""
        unattended_mode(results, permanent, to_email, args.no_email, dry_run=args.dry_run)
    else:
        clean_result = interactive_mode(results, permanent)
        reporter.print_summary(clean_result)


if __name__ == "__main__":
    main()
