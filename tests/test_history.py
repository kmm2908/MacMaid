import json
from unittest.mock import patch
from cleaner import CleanResult
import history


def test_record_appends_entry(tmp_path):
    hist_file = str(tmp_path / "history.json")
    result = CleanResult(moved=3, bytes_freed=1024 * 500, errors=0)
    with patch("history.HISTORY_PATH", hist_file):
        history.record(result)
    entries = json.loads((tmp_path / "history.json").read_text())
    assert len(entries) == 1
    assert entries[0]["items_cleaned"] == 3
    assert entries[0]["bytes_freed"] == 1024 * 500
    assert entries[0]["dry_run"] is False


def test_record_dry_run_flag(tmp_path):
    hist_file = str(tmp_path / "history.json")
    result = CleanResult()
    with patch("history.HISTORY_PATH", hist_file):
        history.record(result, dry_run=True)
    entries = json.loads((tmp_path / "history.json").read_text())
    assert entries[0]["dry_run"] is True


def test_record_caps_at_max_entries(tmp_path):
    hist_file = str(tmp_path / "history.json")
    result = CleanResult()
    with patch("history.HISTORY_PATH", hist_file), \
         patch("history.MAX_ENTRIES", 3):
        for _ in range(5):
            history.record(result)
    entries = json.loads((tmp_path / "history.json").read_text())
    assert len(entries) == 3


def test_load_returns_empty_when_missing(tmp_path):
    with patch("history.HISTORY_PATH", str(tmp_path / "nope.json")):
        assert history.load() == []


def test_format_history_no_entries(tmp_path):
    with patch("history.HISTORY_PATH", str(tmp_path / "nope.json")):
        out = history.format_history()
    assert "No run history" in out


def test_format_history_shows_entries(tmp_path):
    hist_file = str(tmp_path / "history.json")
    result = CleanResult(moved=5, bytes_freed=2 * 1024 * 1024, errors=1)
    with patch("history.HISTORY_PATH", hist_file):
        history.record(result)
        out = history.format_history()
    assert "5 items" in out
    assert "2 MB" in out
    assert "1 error" in out
