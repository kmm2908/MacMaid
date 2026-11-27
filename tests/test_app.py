"""The full app: the page scans, reports and cleans every category (card lniVMHcS)."""
import json
import re
import time
from unittest.mock import patch

import pytest

import cleaner
import main
import reviewer


def result(category, risk, action, items, suggestion=""):
    return {"category": category, "risk": risk, "action": action, "items": items,
            "total_size_bytes": sum(i["size_bytes"] for i in items), "suggestion": suggestion}


def item(path, size=10):
    return {"path": path, "label": path.rsplit("/", 1)[-1], "size_bytes": size, "meta": {}}


RESULTS = {
    "caches": result("Caches", "safe", "trash", [item("/c/a"), item("/c/b")], "Clear caches"),
    "trash": result("Trash", "safe", "empty-trash", [item("/u/.Trash", 99)], "Empty old Trash"),
    "large_files": result("Large & Old Files", "review", "trash", [item("/d/big.dmg", 500)]),
    "memory": result("Memory", "inform-only", "none", [item("memory", 0)], "Memory pressure: normal"),
    "ios_backups": result("iOS Backups", "inform-only", "none", [], "No iOS backups found"),
}


def scan_one(name):
    return json.loads(json.dumps(RESULTS[name]))


def token(client):
    return re.search(r"var TOKEN='([^']+)'", client.get("/").get_data(as_text=True)).group(1)


def post(client, url, body=None, **headers):
    return client.post(url, json=body or {}, headers={"X-MacMaid-Token": token(client), **headers})


@pytest.fixture
def scanned(tmp_path):
    """A full-app client whose first scan has finished; the results file is a temp file."""
    path = tmp_path / "results.json"
    with patch("reviewer.RESULTS_PATH", path):
        client = reviewer._make_app({}, scan=scan_one, modules=list(RESULTS)).test_client()
        assert post(client, "/api/scan").status_code == 202
        wait_for_scan(client)
        yield client, path


def wait_for_scan(client):
    for _ in range(100):
        state = client.get("/api/state").get_json()
        if not state["scanning"]:
            return state
        time.sleep(0.02)
    raise AssertionError("scan never finished")


def test_a_fresh_app_has_not_scanned_and_says_it_can():
    state = reviewer._make_app({}, scan=scan_one, modules=list(RESULTS)).test_client().get("/api/state").get_json()
    assert (state["can_scan"], state["scanning"], state["scan_id"], state["categories"]) == (True, False, 0, [])


def test_the_review_page_cannot_scan():
    client = reviewer._make_app({"Duplicates": [item("/d/x")]}).test_client()
    state = client.get("/api/state").get_json()
    assert state["can_scan"] is False
    assert [(c["name"], c["action"], c["tab"]) for c in state["categories"]] == [("Duplicates", "trash", True)]
    assert post(client, "/api/scan").status_code == 404


def test_a_scan_reports_every_category_and_saves_the_results(scanned):
    client, path = scanned
    state = client.get("/api/state").get_json()
    assert state["scan_id"] == 1
    assert [p["status"] for p in state["progress"]] == ["done"] * len(RESULTS)
    rows = {c["name"]: (c["risk"], c["action"], c["count"], c["size"], c["tab"]) for c in state["categories"]}
    assert rows == {
        "Caches": ("safe", "trash", 2, 20, True),
        "Trash": ("safe", "empty-trash", 1, 99, True),
        "Large & Old Files": ("review", "trash", 1, 500, True),
        "Memory": ("inform-only", "none", 1, 0, True),
        "iOS Backups": ("inform-only", "none", 0, 0, False),
    }
    assert [r["category"] for r in json.loads(path.read_text())] == [r["category"] for r in RESULTS.values()]


def test_a_module_that_fails_is_reported_and_the_scan_goes_on(tmp_path):
    def flaky(name):
        if name == "caches":
            raise RuntimeError("boom")
        return scan_one(name)
    with patch("reviewer.RESULTS_PATH", tmp_path / "r.json"):
        client = reviewer._make_app({}, scan=main._scan_module_with(flaky), modules=list(RESULTS)).test_client()
        post(client, "/api/scan")
        state = wait_for_scan(client)
    caches = next(c for c in state["categories"] if c["name"] == "caches")
    assert (caches["action"], caches["suggestion"]) == ("none", "Error: boom")
    assert len(state["categories"]) == len(RESULTS)


def test_a_second_scan_is_refused_while_one_runs(tmp_path):
    release = __import__("threading").Event()

    def slow(name):
        release.wait(5)
        return scan_one(name)
    with patch("reviewer.RESULTS_PATH", tmp_path / "r.json"):
        client = reviewer._make_app({}, scan=slow, modules=["caches"]).test_client()
        assert post(client, "/api/scan").status_code == 202
        assert post(client, "/api/scan").status_code == 409
        refused = post(client, "/api/delete", {"tab": "Caches", "paths": ["/c/a"]})
        release.set()
        wait_for_scan(client)
    assert refused.status_code == 409


def test_each_item_goes_to_the_cleaner_with_its_categorys_action(scanned):
    client, _ = scanned
    with patch("reviewer.cleaner_mod.clean_items", return_value=cleaner.CleanResult()) as clean:
        post(client, "/api/delete", {"tab": "Caches", "paths": ["/c/a"]})
        post(client, "/api/delete", {"tab": "Trash", "paths": ["/u/.Trash"], "empty_trash": True})
    assert [[(i["path"], i["action"]) for i in c.args[0]] for c in clean.call_args_list] == [
        [("/c/a", "trash")], [("/u/.Trash", "empty-trash")]]


def test_emptying_the_trash_needs_its_own_confirmation(scanned):
    client, _ = scanned
    with patch("reviewer.cleaner_mod.clean_items") as clean:
        resp = post(client, "/api/delete", {"tab": "Trash", "paths": ["/u/.Trash"]})
        untabbed = post(client, "/api/delete", {"paths": ["/u/.Trash"]})
    assert (resp.status_code, untabbed.status_code) == (400, 400)
    assert "confirm" in resp.get_json()["error"]
    clean.assert_not_called()


def test_information_only_categories_cannot_be_deleted(scanned):
    client, _ = scanned
    with patch("reviewer.cleaner_mod.clean_items") as clean:
        resp = post(client, "/api/delete", {"tab": "Memory", "paths": ["memory"]})
    assert resp.status_code == 400
    clean.assert_not_called()


def test_the_browser_never_deletes_permanently(scanned):
    client, _ = scanned
    with patch("reviewer.cfg.get", side_effect=lambda k: True if k == "permanent_delete" else 3), \
         patch("reviewer.cleaner_mod.clean_items", return_value=cleaner.CleanResult()) as clean:
        post(client, "/api/delete", {"tab": "Large & Old Files", "paths": ["/d/big.dmg"]})
    assert clean.call_args.kwargs == {"permanent": False, "trash_retention_days": 3}


def test_a_path_is_only_taken_from_the_tab_it_was_chosen_in(scanned):
    client, _ = scanned
    with patch("reviewer.cleaner_mod.clean_items", return_value=cleaner.CleanResult()) as clean:
        post(client, "/api/delete", {"tab": "Caches", "paths": ["/d/big.dmg", "/c/b"]})
    assert [i["path"] for i in clean.call_args.args[0]] == ["/c/b"]


def test_a_post_from_another_origin_is_refused_even_with_the_token(scanned):
    client, _ = scanned
    with patch("reviewer.cleaner_mod.clean_items") as clean:
        resp = post(client, "/api/delete", {"tab": "Caches", "paths": ["/c/a"]}, Origin="https://evil.example")
        null = post(client, "/api/scan", Origin="null")
    assert (resp.status_code, null.status_code) == (403, 403)
    clean.assert_not_called()


def test_a_post_from_the_page_itself_is_accepted(scanned):
    client, _ = scanned
    with patch("reviewer.cleaner_mod.clean_items", return_value=cleaner.CleanResult()):
        resp = post(client, "/api/delete", {"tab": "Caches", "paths": ["/c/a"]}, Origin="http://localhost:5999")
    assert resp.status_code == 200


@pytest.mark.parametrize("argv, mode", [
    ([], "browser"),
    (["--modules", "caches"], "browser"),
    (["--terminal"], "terminal"),
    (["--permanent"], "terminal"),
])
def test_running_macmaid_opens_the_browser_unless_asked_for_the_terminal(argv, mode):
    with patch("sys.argv", ["main.py", *argv]), patch("main.reviewer.start_app") as app, \
         patch("main.run_scan", return_value=[]), patch("main.interactive_mode") as terminal, \
         patch("main.reporter"):
        main.main()
    assert (app.called, terminal.called) == (mode == "browser", mode == "terminal")
    if argv[:1] == ["--modules"]:
        assert app.call_args.args[0] == ["caches"]


def test_a_trash_folder_that_was_only_partly_emptied_stays_listed(scanned):
    client, _ = scanned
    partial = cleaner.CleanResult(moved=1, errors=1, moved_paths=["/u/.Trash"],
                                  error_paths=[("/u/.Trash/locked", "Permission denied")])
    with patch("reviewer.cleaner_mod.clean_items", return_value=partial):
        post(client, "/api/delete", {"tab": "Trash", "paths": ["/u/.Trash"], "empty_trash": True})
    assert [i["path"] for i in client.get("/api/files/Trash").get_json()] == ["/u/.Trash"]


def test_done_does_not_stop_a_running_scan(tmp_path):
    release = __import__("threading").Event()
    with patch("reviewer.RESULTS_PATH", tmp_path / "r.json"), patch("reviewer.os.kill") as kill:
        client = reviewer._make_app({}, scan=lambda n: (release.wait(5), scan_one(n))[1],
                                    modules=["caches"]).test_client()
        post(client, "/api/scan")
        resp = post(client, "/api/quit")
        release.set()
        wait_for_scan(client)
    assert resp.status_code == 409
    kill.assert_not_called()


def test_a_scan_that_cannot_be_saved_says_so_and_leaves_the_old_file(tmp_path):
    target = tmp_path / "missing-dir" / "r.json"
    with patch("reviewer.RESULTS_PATH", target):
        client = reviewer._make_app({}, scan=scan_one, modules=["caches"]).test_client()
        post(client, "/api/scan")
        state = wait_for_scan(client)
    assert state["save_failed"] is True
    assert not target.exists()


def test_the_page_is_told_exactly_which_paths_left_the_list(scanned):
    client, _ = scanned
    partial = cleaner.CleanResult(moved=1, errors=1, moved_paths=["/u/.Trash"],
                                  error_paths=[("/u/.Trash/locked", "Permission denied")])
    with patch("reviewer.cleaner_mod.clean_items", return_value=partial):
        resp = post(client, "/api/delete", {"tab": "Trash", "paths": ["/u/.Trash"], "empty_trash": True})
    assert resp.get_json()["removed_paths"] == []


def test_permanent_delete_in_config_keeps_the_terminal():
    with patch("sys.argv", ["main.py"]), patch("main.reviewer.start_app") as app, \
         patch("main.cfg.get", side_effect=lambda k: k == "permanent_delete" or None), \
         patch("main.run_scan", return_value=[]), patch("main.interactive_mode") as terminal, \
         patch("main.reporter"):
        main.main()
    assert (app.called, terminal.called) == (False, True)
    assert terminal.call_args.args[1] is True


@pytest.mark.parametrize("argv", [["--dry-run"], ["--dry-run", "--terminal"], ["--dry-run", "--review"]])
def test_a_dry_run_that_would_clean_is_refused(argv):
    with patch("sys.argv", ["main.py", *argv]), patch("main.reviewer.start_app") as app, \
         patch("main.reviewer.start") as review, patch("main.interactive_mode") as terminal, \
         patch("main.run_scan") as scan, pytest.raises(SystemExit) as stop:
        main.main()
    assert stop.value.code == 2
    assert not (app.called or review.called or terminal.called or scan.called)
