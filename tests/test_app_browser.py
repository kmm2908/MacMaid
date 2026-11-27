"""The full app in headless Chrome: scan, summary, every kind of category. Nothing reaches the Trash."""
import threading
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

import cleaner
import reviewer
from tests.test_app import RESULTS, scan_one


class App:
    """The real app on a real port; each scan waits at its first module until `release` is set."""

    def __init__(self, tmp_path):
        self.release = threading.Event()
        self.scans = 0

        def gated(name):
            if name == next(iter(RESULTS)):
                self.scans += 1
                self.release.wait(10)
            return scan_one(name)

        self.patch = patch("reviewer.RESULTS_PATH", tmp_path / "results.json")
        self.patch.start()
        self.server = make_server("localhost", 0, reviewer._make_app({}, scan=gated, modules=list(RESULTS)),
                                  threaded=True)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://localhost:{self.server.server_port}/"

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.patch.stop()


def test_the_page_scans_on_opening_then_summarises_every_category(tmp_path):
    app = App(tmp_path)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(app.url)
            expect(page.locator("#progressHead")).to_have_text("Scanning… 0 of 5 done")
            expect(page.locator("#scanBtn")).to_be_disabled()
            app.release.set()
            expect(page.locator(".tab-btn.active")).to_contain_text("Summary")
            rows = page.locator("#tbody tr").all_inner_texts()
            tabs = page.locator(".tab-btn").evaluate_all("bs => bs.map(b => b.dataset.tab)")
            browser.close()
    finally:
        app.close()

    assert app.scans == 1
    assert [r.split("\t")[:3] for r in rows] == [
        ["Caches", "Safe to clean", "2"], ["Trash", "Empty old Trash", "1"],
        ["Large & Old Files", "You choose", "1"], ["Memory", "Information only", "1"],
        ["iOS Backups", "Information only", "0"]]
    assert tabs == ["Summary", "Caches", "Trash", "Large & Old Files", "Memory"]


def test_information_has_no_delete_control_and_the_trash_its_own_confirmation(tmp_path):
    app = App(tmp_path)
    app.release.set()
    messages = []
    try:
        with patch("reviewer.cleaner_mod.clean_items", return_value=cleaner.CleanResult()) as clean, \
                sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(app.url)
            page.click('.tab-btn[data-tab="Memory"]')
            page.wait_for_selector('#tbody tr[data-path="memory"]')
            memory = (page.locator("#tbody input").count(), page.locator("#tbody .reveal").count(),
                      page.is_visible("#trashBtn"), page.is_visible("#emptyBtn"), page.inner_text("#note"))

            page.click('.tab-btn[data-tab="Trash"]')
            page.wait_for_selector('#tbody tr[data-path="/u/.Trash"]')
            trash = (page.locator("#tbody input").count(), page.is_visible("#trashBtn"),
                     page.inner_text("#emptyBtn"))
            page.once("dialog", lambda d: (messages.append(d.message), d.dismiss()))
            page.click("#emptyBtn")
            page.wait_for_timeout(300)
            assert not clean.called
            page.once("dialog", lambda d: (messages.append(d.message), d.accept()))
            page.click("#emptyBtn")
            expect(page.locator("#summary")).to_have_text("Done.")
            browser.close()
    finally:
        app.close()

    assert memory == (0, 0, False, False, "Memory pressure: normal")
    assert trash == (0, False, "Empty old Trash (99 B)")
    assert "cannot be undone" in messages[0] and "more than 7 days" in messages[0]
    assert [(i["path"], i["action"]) for i in clean.call_args.args[0]] == [("/u/.Trash", "empty-trash")]


def test_a_safe_category_is_chosen_and_trashed_like_a_review_one(tmp_path):
    app = App(tmp_path)
    app.release.set()
    moved = cleaner.CleanResult(moved=1, bytes_freed=10, moved_paths=["/c/a"])
    try:
        with patch("reviewer.cleaner_mod.clean_items", return_value=moved) as clean, sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.on("dialog", lambda d: d.accept())
            page.goto(app.url)
            page.click('#tbody button.open-tab:text("Caches")')
            page.check('#tbody tr[data-path="/c/a"] input')
            page.click("#trashBtn")
            expect(page.locator("#summary .freed")).to_contain_text("Freed 10 B")
            expect(page.locator('.tab-btn[data-tab="Caches"] .badge')).to_have_text("1")
            page.click('.tab-btn[data-tab="Summary"]')
            summary_caches = page.locator("#tbody tr").first.inner_text()
            browser.close()
    finally:
        app.close()

    assert [(i["path"], i["action"]) for i in clean.call_args.args[0]] == [("/c/a", "trash")]
    assert summary_caches.split("\t")[2:4] == ["1", "10 B"]


def test_scan_again_runs_a_new_scan(tmp_path):
    app = App(tmp_path)
    app.release.set()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            page.goto(app.url)
            expect(page.locator("#scanBtn")).to_be_enabled()
            page.click("#scanBtn")
            expect(page.locator(".tab-btn.active")).to_contain_text("Summary")
            expect(page.locator("#scanBtn")).to_be_enabled()
            page.reload()
            expect(page.locator(".tab-btn.active")).to_contain_text("Summary")
            browser.close()
    finally:
        app.close()

    assert app.scans == 2


def test_a_slow_tab_does_not_fill_the_tab_opened_after_it(tmp_path):
    app = App(tmp_path)
    app.release.set()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome")
            page = browser.new_page()
            hold = threading.Event()

            @app.server.app.before_request
            def slow_caches():
                if reviewer.request.path == "/api/files/Caches":
                    hold.wait(5)

            page.goto(app.url)
            page.wait_for_selector("button.open-tab")
            page.click('.tab-btn[data-tab="Caches"]')
            page.click('.tab-btn[data-tab="Large & Old Files"]')
            page.wait_for_selector('#tbody tr[data-path="/d/big.dmg"]')
            hold.set()
            page.wait_for_timeout(500)
            rows = page.locator("#tbody tr").evaluate_all("rs => rs.map(r => r.dataset.path)")
            active = page.inner_text(".tab-btn.active")
            page.click('.tab-btn[data-tab="Caches"]')
            expect(page.locator("#tbody tr")).to_have_count(2)
            browser.close()
    finally:
        app.close()

    assert rows == ["/d/big.dmg"]
    assert "Large & Old Files" in active
