import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import main


def test_save_results_writes_json(tmp_path):
    results = [{"category": "Large & Old Files", "items": [], "risk": "review"}]
    fake_path = tmp_path / "results.json"
    with patch.object(main, "RESULTS_PATH", fake_path):
        main.save_results(results)
    assert json.loads(fake_path.read_text()) == results


def test_save_results_overwrites_existing(tmp_path):
    fake_path = tmp_path / "results.json"
    fake_path.write_text('{"old": true}')
    results = [{"category": "caches", "items": []}]
    with patch.object(main, "RESULTS_PATH", fake_path):
        main.save_results(results)
    assert json.loads(fake_path.read_text()) == results


def test_review_exits_if_no_results_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "nonexistent.json")
    monkeypatch.setattr(sys, "argv", ["main.py", "--review"])
    with pytest.raises(SystemExit):
        main.main()


def test_review_calls_reviewer_start_with_large_files_items(tmp_path, monkeypatch):
    items = [{"path": "/tmp/a.dmg", "label": "a.dmg", "size_bytes": 1_000_000_000, "meta": {}}]
    results = [
        {"category": "Large & Old Files", "risk": "review", "items": items,
         "total_size_bytes": 1_000_000_000, "suggestion": "", "action": "trash"},
        {"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
         "suggestion": "", "action": "trash"},
    ]
    fake_path = tmp_path / "results.json"
    fake_path.write_text(json.dumps(results))

    monkeypatch.setattr(main, "RESULTS_PATH", fake_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "--review"])

    started = []
    with patch("main.reviewer.start", side_effect=lambda i: started.append(i)):
        with pytest.raises(SystemExit):
            main.main()

    assert len(started) == 1
    assert started[0] == {"Large & Old Files": items}


def test_review_exits_if_large_files_empty(tmp_path, monkeypatch):
    results = [{"category": "Large & Old Files", "risk": "review", "items": [],
                "total_size_bytes": 0, "suggestion": "", "action": "trash"}]
    fake_path = tmp_path / "results.json"
    fake_path.write_text(json.dumps(results))

    monkeypatch.setattr(main, "RESULTS_PATH", fake_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "--review"])
    with pytest.raises(SystemExit):
        main.main()


def test_unattended_mode_saves_results(tmp_path, monkeypatch):
    """save_results() is called during unattended_mode()."""
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    with patch("main.reporter.print_unattended_report", return_value="report"), \
         patch("main.history.record"), \
         patch("main.emailer.send_report"):
        main.unattended_mode(results, False, "", no_email=True)

    assert (tmp_path / "results.json").exists()
    saved = json.loads((tmp_path / "results.json").read_text())
    assert saved == results


def test_unattended_email_includes_review_link_when_large_files_present(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    items = [{"path": "/tmp/a.dmg", "label": "a.dmg", "size_bytes": 1_000_000_000, "meta": {}}]
    results = [
        {"category": "Large & Old Files", "risk": "review", "items": items,
         "total_size_bytes": 1_000_000_000, "suggestion": "", "action": "trash"},
    ]
    sent_bodies = []
    with patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.history.record"), \
         patch("main._start_review_server"), \
         patch("main.emailer.send_report", side_effect=lambda s, b, t, **kw: sent_bodies.append(b)):
        main.unattended_mode(results, False, "test@example.com", no_email=False)

    assert len(sent_bodies) == 1
    assert f"Review files: http://localhost:{main.reviewer.REVIEW_PORT}" in sent_bodies[0]


def test_unattended_email_no_review_link_when_no_large_files(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    sent_bodies = []
    with patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.history.record"), \
         patch("main.emailer.send_report", side_effect=lambda s, b, t, **kw: sent_bodies.append(b)):
        main.unattended_mode(results, False, "test@example.com", no_email=False)

    assert len(sent_bodies) == 1
    assert "localhost" not in sent_bodies[0]


def test_unattended_dry_run_does_not_save_results(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    with patch("main.reporter.print_unattended_report", return_value="report"), \
         patch("main.history.record"), \
         patch("main.emailer.send_report"):
        main.unattended_mode(results, False, "", no_email=True, dry_run=True)

    assert not (tmp_path / "results.json").exists()


def _result(category: str, risk: str, action: str = "trash", items: int = 1) -> dict:
    return {"category": category, "risk": risk, "action": action,
            "items": [{"path": f"/tmp/{category}", "label": category, "size_bytes": 1,
                       "meta": {}}][:items]}


def test_every_trashable_review_category_with_items_is_offered_for_review():
    results = [
        _result("Large & Old Files", "review"),
        _result("Mail Store", "review"),
        _result("iOS Backups", "review"),
        _result("A Future Module", "review"),
        _result("Duplicates", "review", items=0),
        _result("Caches", "safe"),
        _result("Login Items", "inform-only", action="none"),
    ]
    assert list(main._load_review_categories(results)) == [
        "Large & Old Files", "Mail Store", "iOS Backups", "A Future Module"]


@pytest.mark.parametrize("action", ["empty-trash", "none"])
def test_review_category_the_page_cannot_act_on_correctly_is_not_offered(action):
    # The page can only move to Trash, so any other action must stay out of it.
    assert main._load_review_categories([_result("Large & Old Files", "review", action=action)]) == {}


def test_real_mail_and_ios_scan_results_reach_the_review_page(tmp_path, monkeypatch):
    for module, attr in ((main.mail, "MAIL_DIR"), (main.ios_backups, "BACKUP_DIR")):
        folder = tmp_path / attr / "one"
        folder.mkdir(parents=True)
        (folder / "x.bin").write_bytes(b"x")
        monkeypatch.setattr(module, attr, str(tmp_path / attr))
    cats = main._load_review_categories([main.mail.scan(), main.ios_backups.scan()])
    assert list(cats) == ["Mail Store", "iOS Backups"]
