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
    with patch.dict("sys.modules", {"reviewer": MagicMock(start=lambda i: started.append(i))}):
        with pytest.raises(SystemExit):
            main.main()

    assert len(started) == 1
    assert started[0] == items


def test_review_exits_if_large_files_empty(tmp_path, monkeypatch):
    results = [{"category": "Large & Old Files", "risk": "review", "items": [],
                "total_size_bytes": 0, "suggestion": "", "action": "trash"}]
    fake_path = tmp_path / "results.json"
    fake_path.write_text(json.dumps(results))

    monkeypatch.setattr(main, "RESULTS_PATH", fake_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "--review"])
    with pytest.raises(SystemExit):
        main.main()
