#!/usr/bin/env python3
import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import questionary
from rich.console import Console

import config as cfg
import config_cli
import reporter
import cleaner as cleaner_mod
import emailer
import scheduler
import history
import reviewer
import storage_watch

from modules import (
    caches, logs, trash, large_files, duplicates,
    dev_junk, browsers, mail, login_items, disk_health, memory, thermal,
    ios_backups, xcode_sims, downloads,
)

console = Console()

RESULTS_PATH = Path.home() / "Library" / "Logs" / "mac-maid-last-results.json"


ERROR_LOG_PATH = Path.home() / "Library" / "Logs" / "mac-maid-error.log"


def save_results(results: list[dict]) -> None:
    RESULTS_PATH.write_text(json.dumps(results))


def log_errors(clean_result) -> None:
    """Append per-path failures so a rising error count can be diagnosed.

    error_paths was collected and discarded, which is why 602 nightly failures
    went unnoticed with an empty error log.
    """
    if not clean_result.error_paths:
        return
    stamp = date.today().isoformat()
    try:
        ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ERROR_LOG_PATH, "a") as f:
            for path, err in clean_result.error_paths:
                f.write(f"{stamp}\t{path}\t{err}\n")
    except OSError:
        pass  # logging must never break the run


MODULES = {
    "caches": caches.scan,
    "logs": logs.scan,
    "trash": trash.scan,
    "downloads": downloads.scan,  # after trash: see tests/test_downloads.py
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


def _with_action(result: dict, items: list[dict] | None = None) -> list[dict]:
    """Tag each item with its module's action so the cleaner can dispatch on it.

    Without this the Trash module's "empty-trash" action is lost when items are
    flattened, and the cleaner falls back to send2trash(~/.Trash).
    """
    return [{**item, "action": result["action"]}
            for item in (result["items"] if items is None else items)]


def _trash_retention_days() -> int:
    return cfg.get("trash_retention_days") or cleaner_mod.DEFAULT_TRASH_RETENTION_DAYS


def _without_moved(results: list[dict], moved_paths: list[str]) -> list[dict]:
    """Drop review candidates an automatic clean has already taken (Downloads overlaps them)."""
    gone = set(moved_paths)
    kept_results = []
    for r in results:
        if r["risk"] == "review":
            items = [i for i in r["items"] if i["path"] not in gone]
            r = {**r, "items": items,
                 "total_size_bytes": sum(i.get("size_bytes", 0) for i in items)}
        kept_results.append(r)
    return kept_results


def interactive_mode(results: list[dict], permanent: bool) -> cleaner_mod.CleanResult:
    total_result = cleaner_mod.CleanResult()

    for scanned in results:
        r = _without_moved([scanned], total_result.moved_paths)[0]
        if r["risk"] == "inform-only" or not r["items"]:
            continue

        if r["risk"] == "safe":
            size = reporter.format_size(r["total_size_bytes"])
            confirm = questionary.confirm(
                f"Clean {r['category']}? ({size})"
            ).ask()
            if confirm:
                cr = cleaner_mod.clean_items(_with_action(r), permanent=permanent,
                                             trash_retention_days=_trash_retention_days())
                total_result.moved += cr.moved
                total_result.errors += cr.errors
                total_result.bytes_freed += cr.bytes_freed
                total_result.skipped += cr.skipped
                total_result.changed_paths.extend(cr.changed_paths)
                total_result.moved_paths.extend(cr.moved_paths)

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
                cr = cleaner_mod.clean_items(_with_action(r, to_clean), permanent=permanent,
                                             trash_retention_days=_trash_retention_days())
                total_result.moved += cr.moved
                total_result.errors += cr.errors
                total_result.bytes_freed += cr.bytes_freed
                total_result.skipped += cr.skipped
                total_result.changed_paths.extend(cr.changed_paths)

    return total_result


def _port_listeners() -> list[str]:
    """PIDs listening on the review port. Listeners only: a plain port match also lists the browser."""
    found = subprocess.run(
        ["lsof", "-ti", f"tcp:{reviewer.REVIEW_PORT}", "-sTCP:LISTEN"], capture_output=True, text=True,
    )
    return found.stdout.split()


def _stop_old_review_server() -> bool:
    """Stop the review server this checkout started earlier. True once the port is free.

    Not through /api/quit, which needs that server's own token. Anything else on the port is left alone.
    """
    ours = f"{Path(__file__).resolve()} --serve"
    for pid in _port_listeners():
        command = subprocess.run(
            ["ps", "-ww", "-o", "command=", "-p", pid], capture_output=True, text=True,
        ).stdout.strip()
        if command.endswith(ours):
            with contextlib.suppress(ProcessLookupError):
                os.kill(int(pid), signal.SIGTERM)
    for _ in range(20):
        if not _port_listeners():
            return True
        time.sleep(0.25)
    return False


def _start_review_server() -> bool:
    """Replace any earlier review server. True once the new one answers."""
    try:
        if not _stop_old_review_server():
            return False
        server = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    # Wait up to 10s for the server to be ready before emailing the link
    for _ in range(20):
        if server.poll() is not None:
            return False
        try:
            urllib.request.urlopen(f"http://localhost:{reviewer.REVIEW_PORT}/", timeout=0.5)
            return True
        except OSError:
            time.sleep(0.5)
    return False


def _report_html(report_text: str, review_url: str | None = None) -> str:
    """The whole email as a dark 24px document.

    A full document, not a fragment: the global sender inserts its ACTION block just
    inside <body>, so that block inherits the dark canvas too. Hexes are copied from
    tokens.css because email clients do not resolve CSS variables.
    """
    escaped = report_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    button = ""
    if review_url:
        button = (
            f'<hr style="margin:24px 0;border:0;border-top:1px solid #3d4a5a">'
            f'<p><a class="btn" role="button" href="{review_url}" style="display:inline-block;padding:12px 24px;'
            f'background:#12558c;color:#ffffff;border:2px solid #8fd3ff;text-decoration:none;border-radius:12px;'
            f'font-weight:bold">&#x1f9f9; Review Files &rarr;</a></p>'
            f'<p>Opens on this Mac while MacMaid review server is running.</p>'
        )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="color-scheme" content="dark"></head>'
        '<body style="margin:0;padding:40px;background:#07090c;color:#f2f6fa;'
        'font-family:sans-serif;font-size:24px;line-height:1.5">'
        f'<pre style="font-family:monospace;font-size:24px;white-space:pre-wrap;overflow-wrap:anywhere">{escaped}</pre>'
        f'{button}</body></html>'
    )


def unattended_mode(results: list[dict], permanent: bool, to_email: str, no_email: bool, dry_run: bool = False) -> None:
    items_to_clean = [
        item
        for r in results
        if r["risk"] == "safe" and r["action"] != "none"
        for item in _with_action(r)
    ]
    if dry_run:
        clean_result = cleaner_mod.CleanResult()
    else:
        clean_result = cleaner_mod.clean_items(
            items_to_clean, permanent=permanent,
            trash_retention_days=_trash_retention_days(),
        )
        log_errors(clean_result)
        results = _without_moved(results, clean_result.moved_paths)
    report_text = reporter.print_unattended_report(results, clean_result, dry_run=dry_run)

    if not dry_run:
        save_results(results)
    history.record(clean_result, dry_run=dry_run)

    if not no_email and to_email:
        review_url = None
        if _load_review_categories(results):
            if _start_review_server():
                review_url = f"http://localhost:{reviewer.REVIEW_PORT}"
                report_text += f"\n\n---\nReview files: {review_url}"
            else:
                report_text += "\n\n---\nThe review page did not start. Run main.py --review to open it."
        html_body = _report_html(report_text, review_url)
        prefix = "[DRY RUN] " if dry_run else ""
        subject = f"{prefix}Mac Maid Report — {date.today()} — {reporter.format_size(clean_result.bytes_freed)} freed"
        emailer.send_report(subject, report_text, to_email, html_body=html_body)


def _load_review_categories(results: list[dict]) -> dict[str, list[dict]]:
    """Every review-risk category with items. The page can only move to Trash."""
    return {
        r["category"]: r["items"]
        for r in results
        if r.get("risk") == "review" and r.get("action") == "trash" and r.get("items")
    }


def main() -> None:
    # A subcommand with its own options; everything else here is a flag.
    if sys.argv[1:2] == ["config"]:
        sys.exit(config_cli.run(sys.argv[2:], list(MODULES)))

    parser = argparse.ArgumentParser(
        description="Mac Maid — macOS maintenance tool",
        epilog="View or change settings: main.py config --help",
    )
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
    parser.add_argument("--storage-check", action="store_true", help="Alert if the main disk is low on space")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.storage_check:
        storage_watch.check()
        return

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
            console.print("[yellow]Nothing to review in the last scan.[/yellow]")
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
