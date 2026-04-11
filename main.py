#!/usr/bin/env python3
import argparse
import sys
from datetime import date

import questionary
from rich.console import Console

import config as cfg
import reporter
import cleaner as cleaner_mod
import emailer
import scheduler

from modules import (
    caches, logs, trash, large_files, duplicates,
    dev_junk, browsers, mail, login_items, disk_health, memory, thermal
)

console = Console()

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


def unattended_mode(results: list[dict], permanent: bool, to_email: str, no_email: bool) -> None:
    items_to_clean = [
        item
        for r in results
        if r["risk"] == "safe" and r["action"] != "none"
        for item in r["items"]
    ]
    clean_result = cleaner_mod.clean_items(items_to_clean, permanent=permanent)
    report_text = reporter.print_unattended_report(results, clean_result)

    if not no_email and to_email:
        subject = f"Mac Maid Report — {date.today()} — {reporter.format_size(clean_result.bytes_freed)} freed"
        emailer.send_report(subject, report_text, to_email)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mac Maid — macOS maintenance tool")
    parser.add_argument("--unattended", action="store_true", help="Run silently and email report")
    parser.add_argument("--modules", nargs="+", help="Run specific modules only")
    parser.add_argument("--permanent", action="store_true", help="Delete permanently instead of Trash")
    parser.add_argument("--no-email", action="store_true", help="Skip email in unattended mode")
    parser.add_argument("--schedule", metavar="HH:MM", help="Install nightly LaunchAgent")
    parser.add_argument("--unschedule", action="store_true", help="Remove LaunchAgent")
    parser.add_argument("--schedule-status", action="store_true", help="Show schedule status")
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

    reporter.print_banner()

    enabled = args.modules or [
        name for name in MODULES if cfg.module_enabled(name)
    ]

    results = run_scan(enabled)
    reporter.print_results(results)

    permanent = args.permanent or cfg.get("permanent_delete") or False

    if args.unattended:
        to_email = cfg.get("email_report_to") or ""
        unattended_mode(results, permanent, to_email, args.no_email)
    else:
        clean_result = interactive_mode(results, permanent)
        reporter.print_summary(clean_result)


if __name__ == "__main__":
    main()
