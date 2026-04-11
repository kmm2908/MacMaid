from unittest.mock import patch, MagicMock
from main import run_scan, MODULES

def test_run_scan_returns_results_for_all_modules():
    mock_result = {"category": "Test", "risk": "safe", "items": [],
                   "total_size_bytes": 0, "suggestion": "", "action": "trash"}
    with patch.dict("main.MODULES", {k: MagicMock(return_value=mock_result) for k in MODULES}):
        results = run_scan(enabled_modules=list(MODULES.keys()))
    assert len(results) == len(MODULES)

def test_run_scan_respects_enabled_modules():
    mock_result = {"category": "Test", "risk": "safe", "items": [],
                   "total_size_bytes": 0, "suggestion": "", "action": "trash"}
    with patch.dict("main.MODULES", {k: MagicMock(return_value=mock_result) for k in MODULES}):
        results = run_scan(enabled_modules=["caches"])
    assert len(results) == 1

def test_run_scan_handles_module_error():
    def bad_scan():
        raise RuntimeError("disk error")
    with patch.dict("main.MODULES", {"caches": bad_scan}):
        results = run_scan(enabled_modules=["caches"])
    # Should not crash — error result returned
    assert len(results) == 1
    assert results[0]["category"] == "caches"
