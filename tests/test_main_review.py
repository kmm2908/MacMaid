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
