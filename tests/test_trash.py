from unittest.mock import patch
from modules.trash import scan

def test_scan_reports_trash_size():
    with patch("modules.trash._trash_size", return_value=500 * 1024 * 1024):
        result = scan()
    assert result["category"] == "Trash"
    assert result["risk"] == "safe"
    assert result["action"] == "empty-trash"
    assert result["total_size_bytes"] == 500 * 1024 * 1024
    assert len(result["items"]) == 1
    assert "Trash" in result["items"][0]["label"]

def test_scan_empty_trash():
    with patch("modules.trash._trash_size", return_value=0):
        result = scan()
    assert result["total_size_bytes"] == 0
    assert result["suggestion"] == "Trash is empty"
