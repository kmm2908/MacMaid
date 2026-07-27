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
         patch("main.history.record"):
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
    calls = []
    with patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.history.record"), \
         patch("main._start_review_server"), \
         patch("main.notify.notify", side_effect=lambda **kw: calls.append(kw) or True):
        main.unattended_mode(results, False, "test@example.com", no_email=False)

    assert len(calls) == 1
    assert f"localhost:{main.reviewer.REVIEW_PORT}" in calls[0]["link"]
    assert calls[0]["do_this"]
    assert calls[0]["to"] == ["test@example.com"]


def test_unattended_no_email_when_nothing_reviewable(tmp_path, monkeypatch):
    """No reviewable items -> notify.notify() must not be called (action-only gate)."""
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    with patch("main.reporter.print_unattended_report", return_value="report text"), \
         patch("main.history.record"), \
         patch("main.notify.notify") as mock_notify:
        main.unattended_mode(results, False, "test@example.com", no_email=False)

    mock_notify.assert_not_called()


def test_unattended_dry_run_does_not_save_results(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "RESULTS_PATH", tmp_path / "results.json")
    results = [{"category": "caches", "risk": "safe", "items": [], "total_size_bytes": 0,
                "suggestion": "", "action": "trash"}]
    with patch("main.reporter.print_unattended_report", return_value="report"), \
         patch("main.history.record"):
        main.unattended_mode(results, False, "", no_email=True, dry_run=True)

    assert not (tmp_path / "results.json").exists()
