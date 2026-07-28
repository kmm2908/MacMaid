from unittest.mock import patch

from modules import trash
from modules.trash import scan


def test_scan_reports_reclaimable_trash_size():
    with patch.object(trash, "trash_dirs", return_value=["/fake/.Trash"]), \
         patch.object(trash, "reclaimable_size", return_value=500 * 1024 * 1024):
        result = scan()
    assert result["category"] == "Trash"
    assert result["risk"] == "safe"
    assert result["action"] == "empty-trash"
    assert result["total_size_bytes"] == 500 * 1024 * 1024
    assert len(result["items"]) == 1
    assert "Trash" in result["items"][0]["label"]


def test_scan_with_nothing_past_retention():
    with patch.object(trash, "trash_dirs", return_value=["/fake/.Trash"]), \
         patch.object(trash, "reclaimable_size", return_value=0):
        result = scan()
    assert result["total_size_bytes"] == 0
    assert result["items"] == []
    assert "older than" in result["suggestion"]


def test_scan_aggregates_multiple_volumes():
    with patch.object(trash, "trash_dirs",
                      return_value=["/fake/.Trash", "/Volumes/Ext Data/.Trashes/501"]), \
         patch.object(trash, "reclaimable_size", return_value=1024 * 1024):
        result = scan()
    assert len(result["items"]) == 2
    assert result["total_size_bytes"] == 2 * 1024 * 1024
