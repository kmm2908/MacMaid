"""The review page's own behaviour, driven in headless Chrome. Nothing reaches the Trash."""
import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
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


def test_mail_and_ios_tabs_carry_their_caution_and_own_columns() -> None:
    backup = {"path": "/nowhere/backup", "label": "Old Phone", "size_bytes": 10,
              "meta": {"last_backup": "2025-03-04", "device": "Old Phone"}}
    mail = {"path": "/nowhere/Mail", "label": "Mail Store (1 MB)", "size_bytes": 10, "meta": {}}
    app = reviewer._make_app({"Duplicates": ITEMS, "Mail Store": [mail], "iOS Backups": [backup]})
    server = make_server("localhost", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    seen: dict[str, tuple[str, list[str], str]] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(f"http://localhost:{server.server_port}/")
            for tab, first_path in (("Mail Store", mail["path"]), ("iOS Backups", backup["path"]),
                                    ("Duplicates", ITEMS[0]["path"])):
                page.click(f'.tab-btn[data-tab="{tab}"]')
                # The tab lights up before its rows arrive, so wait for its own row.
                page.wait_for_selector(f'#tbody tr[data-path="{first_path}"]')
                seen[tab] = (page.inner_text("#note"),
                             [h.strip(" ▲▼") for h in
                              page.locator("#thead th").all_inner_texts()[1:-1]],
                             page.inner_text("#tbody tr"))
            browser.close()
    finally:
        server.shutdown()

    assert "whole mail folder" in seen["Mail Store"][0]
    assert seen["Mail Store"][1] == ["Name", "Full Path", "Size"]
    assert "old devices" in seen["iOS Backups"][0]
    assert seen["iOS Backups"][1] == ["Name", "Full Path", "Size", "Last Backup"]
    assert "2025-03-04" in seen["iOS Backups"][2]
    assert seen["Duplicates"][0] == ""


@pytest.mark.parametrize("tab, words", [
    ("Mail Store", ["WHOLE mail folder", "only on this Mac", "delete it permanently"]),
    ("iOS Backups", ["cannot be recreated", "delete it permanently"]),
])
def test_irreplaceable_categories_spell_out_the_loss_before_trashing(
        tab: str, words: list[str]) -> None:
    item = {"path": "/nowhere/folder", "label": "folder", "size_bytes": 10, "meta": {}}
    server = make_server("localhost", 0, reviewer._make_app({tab: [item]}), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    messages: list[str] = []
    try:
        with patch("reviewer.cleaner_mod.clean_items") as clean, sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.on("dialog", lambda d: (messages.append(d.message), d.dismiss()))
            page.goto(f"http://localhost:{server.server_port}/")
            page.check("#tbody tr:first-child input")
            page.click("#trashBtn")
            browser.close()
    finally:
        server.shutdown()

    assert not clean.called
    assert len(messages) == 1
    assert [w for w in words if w not in messages[0]] == []


def test_an_item_left_alone_because_it_changed_is_said_so() -> None:
    server = make_server("localhost", 0, reviewer._make_app({"Mail Store": ITEMS[:1]}), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    left = cleaner.CleanResult(skipped=1, changed_paths=[ITEMS[0]["path"]])
    try:
        with patch("reviewer.cleaner_mod.clean_items", return_value=left), \
             patch("reviewer._persist_results"), sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.on("dialog", lambda d: d.accept())
            page.goto(f"http://localhost:{server.server_port}/")
            page.check("#tbody tr:first-child input")
            page.click("#trashBtn")
            expect(page.locator("#summary")).to_contain_text("changed since the scan")
            expect(page.locator("#tbody tr")).to_have_count(1)
            browser.close()
    finally:
        server.shutdown()


def test_reveal_and_done_work_with_the_pages_own_token() -> None:
    server = make_server("localhost", 0, reviewer._make_app({"Duplicates": ITEMS}), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with patch("reviewer.subprocess.run") as run, patch("reviewer.os.path.exists", return_value=True), \
             patch("reviewer.os.kill") as kill, sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(f"http://localhost:{server.server_port}/")
            with page.expect_response("**/api/reveal") as reveal:
                page.click("#tbody tr:first-child .reveal")
            assert reveal.value.status == 200
            opened = [c for c in run.call_args_list if c[0][0][:2] == ["open", "-R"]]
            assert len(opened) == 1
            page.click("text=Done")
            page.wait_for_selector("text=server stopped")
            page.wait_for_timeout(600)
            kill.assert_called_once()
            browser.close()
    finally:
        server.shutdown()


def test_a_page_from_an_earlier_session_says_to_reload_and_changes_nothing() -> None:
    server = make_server("localhost", 0, reviewer._make_app({"Duplicates": ITEMS}), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with patch("reviewer.cleaner_mod.clean_items") as clean, patch("reviewer.os.kill") as kill, \
             sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.on("dialog", lambda d: d.accept())
            page.goto(f"http://localhost:{server.server_port}/")
            page.wait_for_selector("#tbody tr")
            page.evaluate("TOKEN='from-yesterday'")

            page.check("#tbody tr:first-child input")
            page.click("#trashBtn")
            expect(page.locator("#note .err")).to_contain_text("Reload")
            assert page.locator("#tbody tr").count() == 2
            assert "Freed" not in page.inner_text("#summary")

            page.evaluate("document.getElementById('note').textContent=''")
            page.click("text=Done")
            expect(page.locator("#note .err")).to_contain_text("Reload")
            assert page.locator("text=server stopped").count() == 0
            clean.assert_not_called()
            kill.assert_not_called()
            browser.close()
    finally:
        server.shutdown()


def test_done_does_not_claim_the_server_stopped_when_it_did_not() -> None:
    server = make_server("localhost", 0, reviewer._make_app({"Duplicates": ITEMS}), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.route("**/api/quit", lambda route: route.fulfill(status=500, body="boom"))
            page.goto(f"http://localhost:{server.server_port}/")
            page.wait_for_selector("#tbody tr")
            page.click("text=Done")
            expect(page.locator("#note .err")).to_contain_text("did not stop")
            assert page.locator("text=server stopped").count() == 0
            browser.close()
    finally:
        server.shutdown()
