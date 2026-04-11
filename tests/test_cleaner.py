import os
import tempfile
from unittest.mock import patch, MagicMock
from cleaner import clean_items, CleanResult

def test_clean_items_moves_to_trash(tmp_path):
    f = tmp_path / "junk.log"
    f.write_text("junk")
    items = [{"path": str(f), "size_bytes": 4, "label": "junk.log", "meta": {}}]
    with patch("cleaner.send2trash") as mock_trash:
        result = clean_items(items, permanent=False)
    mock_trash.assert_called_once_with(str(f))
    assert result.moved == 1
    assert result.errors == 0
    assert result.bytes_freed == 4

def test_clean_items_permanent_delete(tmp_path):
    f = tmp_path / "junk.log"
    f.write_text("junk")
    items = [{"path": str(f), "size_bytes": 4, "label": "junk.log", "meta": {}}]
    result = clean_items(items, permanent=True)
    assert not f.exists()
    assert result.moved == 1
    assert result.errors == 0

def test_clean_items_missing_file_counts_as_error():
    items = [{"path": "/nonexistent/file.txt", "size_bytes": 0, "label": "x", "meta": {}}]
    result = clean_items(items, permanent=False)
    assert result.errors == 1
    assert result.moved == 0

def test_clean_items_empty_list():
    result = clean_items([], permanent=False)
    assert result.moved == 0
    assert result.errors == 0
    assert result.bytes_freed == 0
