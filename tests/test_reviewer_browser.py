"""The review page's own behaviour, driven in headless Chrome. Nothing reaches the Trash."""
import json
import threading
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

import cleaner
import reviewer

ITEMS = [{"path": f"/nowhere/{n}.bin", "label": f"{n}.bin", "size_bytes": 10,
          "meta": {"duplicate_of": "/nowhere/keep.bin"}} for n in ("alpha", "beta")]


def test_confirm_warns_about_hidden_selection_and_empty_filter_counts_zero() -> None:
    server = make_server("localhost", 0, reviewer._make_app({"Duplicates": ITEMS}), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    messages: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
            page.goto(f"http://localhost:{server.server_port}/")
            page.check("#tbody tr:first-child input")
            page.click("#trashBtn")
            page.fill("#filter", "no-such-file")
            assert page.inner_text("#count") == "0 of 0 files"
            page.click("#trashBtn")
            browser.close()
    finally:
        server.shutdown()

    assert messages == [
        "Move 1 file(s) to Trash?",
        "Move 1 file(s) to Trash?\n\nHidden by the current filter: 1.",
    ]


def test_trashing_a_shared_file_updates_the_unopened_tab_and_saved_results(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(json.dumps([{"category": c, "items": ITEMS[:1]}
                                   for c in ("Large & Old Files", "Duplicates")]))
    app = reviewer._make_app({"Large & Old Files": ITEMS[:1], "Duplicates": ITEMS[:1]})
    server = make_server("localhost", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    moved = cleaner.CleanResult(moved=1, bytes_freed=10, moved_paths=[ITEMS[0]["path"]])
    try:
        with patch("reviewer.cleaner_mod.clean_items", return_value=moved), \
             patch("reviewer.RESULTS_PATH", results), sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.on("dialog", lambda d: d.accept())
            page.goto(f"http://localhost:{server.server_port}/")
            page.check("#tbody tr:first-child input")
            page.click("#trashBtn")
            page.wait_for_selector("#summary .freed")
            # Tab names arrive sorted, so Duplicates is open and Large is unopened.
            badge = page.locator('.tab-btn[data-tab="Large & Old Files"] .badge')
            expect(badge).to_have_text("0")
            page.fill("#filter", "")
            page.click('.tab-btn[data-tab="Large & Old Files"]')
            expect(page.locator("#count")).to_have_text("0 of 0 files")
            expect(badge).to_have_text("0")
            browser.close()
    finally:
        server.shutdown()

    assert [r["items"] for r in json.loads(results.read_text())] == [[], []]
