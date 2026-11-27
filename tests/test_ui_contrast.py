"""Rendered check of the two surfaces the owner reads: >=24px, >=6:1, canonical controls."""
import json
import re
import threading
from unittest.mock import patch

import pytest
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

import cleaner
import main
import reviewer
from tests import contrast_check

PATH = "/Users/someone/Library/Application Support/AVeryLongVendorName/exports/quarterly-backup-archive-final.dmg"
ITEMS = [{"path": PATH, "label": "quarterly-backup-archive-final.dmg", "size_bytes": 2_000_000_000,
          "meta": {"last_modified": "2025-01-01", "age_days": 365, "duplicate_of": PATH + ".orig"}},
         {"path": "/Users/someone/old.zip", "label": "old.zip", "size_bytes": 500,
          "meta": {"last_modified": "2024-06-01", "age_days": 600}}]


@pytest.fixture(scope="module")
def snapshots(tmp_path_factory):
    """Drive the real review page into each state it can draw and freeze the DOM.

    Delete, reveal and quit are answered by the browser, so nothing is trashed and
    /api/quit cannot SIGINT the test run.
    """
    out = tmp_path_factory.mktemp("ui")
    app = reviewer._make_app({"Large & Old Files": ITEMS, "Duplicates": ITEMS,
                              "iOS Backups": ITEMS})
    server = make_server("localhost", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pages = {}

    def freeze(page, name):
        html = re.sub(r"<script>.*?</script>", "", page.content(), flags=re.S)
        pages[name] = out / f"{name}.html"
        pages[name].write_text(html)

    def answer(status, body):
        return lambda route: route.fulfill(status=status, content_type="application/json",
                                           body=json.dumps(body))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route("**/api/reveal", answer(404, {"error": "File not found on disk"}))
            page.route("**/api/delete", answer(200, {
                "moved": 1, "errors": 1, "bytes_freed": 500, "moved_paths": [],
                "not_found_paths": ["/gone"], "error_paths": [["/denied", "denied"]]}))
            page.route("**/api/quit", answer(200, {"ok": True}))
            page.on("dialog", lambda d: d.accept())
            page.goto(f"http://localhost:{server.server_port}/")
            page.wait_for_selector("#tbody tr")
            freeze(page, "loaded")
            page.click("#tbody tr:first-child input")
            page.click("#tbody tr:first-child .reveal")
            page.wait_for_selector("#toast", state="visible")
            freeze(page, "selected")
            page.click("#trashBtn")
            page.wait_for_selector("#summary .err")
            freeze(page, "after-delete")
            page.click(".tab-btn[data-tab='Duplicates']")
            page.wait_for_selector("text=Duplicate of")
            freeze(page, "duplicates")
            page.click(".tab-btn[data-tab='iOS Backups']")
            page.wait_for_selector("text=Last Backup")
            freeze(page, "ios-backups")
            page.click("text=Done")
            page.wait_for_selector("text=server stopped")
            freeze(page, "stopped")
            browser.close()
    finally:
        server.shutdown()
    return pages


@pytest.mark.parametrize("state", ["loaded", "selected", "after-delete", "duplicates",
                                   "ios-backups", "stopped"])
def test_review_page_is_readable(snapshots, state):
    assert contrast_check.check(snapshots[state]) == []


def canvas(path):
    """The colour the browser paints behind everything: the harness does not judge it."""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        page.goto(path.as_uri())
        colour = page.evaluate("getComputedStyle(document.body).backgroundColor")
        browser.close()
    return colour


def test_review_page_canvas_is_dark(snapshots):
    assert canvas(snapshots["loaded"]) == "rgb(7, 9, 12)"


@pytest.mark.parametrize("review_url", ["http://localhost:5888", None])
def test_report_email_is_readable(tmp_path, review_url):
    page = tmp_path / "email.html"
    body = main._report_html("Mac Maid Report <&>\n" + "=" * 90 + f"\n{PATH}", review_url)
    # Stand in for the global sender, which inserts its ACTION block just inside <body>.
    start = body.index(">", body.index("<body")) + 1
    page.write_text(body[:start] + '<div style="font-size:24px">ACTION: none</div>' + body[start:])
    assert contrast_check.check(page) == []
    assert canvas(page) == "rgb(7, 9, 12)"


@pytest.mark.parametrize("review_url", ["http://localhost:5888", None])
def test_every_report_email_is_sent_as_that_document(review_url):
    cats = {"Large & Old Files": ITEMS} if review_url else {}
    with patch("main.emailer.send_report") as send, patch("main._start_review_server"), \
         patch("main._load_review_categories", return_value=cats), patch("main.history.record"), \
         patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.cleaner_mod.clean_items", return_value=cleaner.CleanResult()), \
         patch("main.log_errors"), patch("main.save_results"):
        main.unattended_mode([], False, "someone@example.com", False, dry_run=True)
    text = send.call_args.args[1]
    assert send.call_args.kwargs["html_body"] == main._report_html(text, review_url)


def test_checker_rejects_a_known_bad_page(tmp_path):
    page = tmp_path / "bad.html"
    page.write_text('<body style="background:#07090c;color:#f2f6fa;padding:40px">'
                    '<p style="font-size:12px">too small</p></body>')
    assert any("below 24px" in line for line in contrast_check.check(page))
