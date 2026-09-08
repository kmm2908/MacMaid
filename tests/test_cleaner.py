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


def test_a_directory_written_to_since_the_scan_is_not_cleaned(tmp_path):
    """The scan and the clean are different moments — seconds apart unattended,
    hours apart behind the review UI. A dependency tree that has been installed
    into since it was judged is in use, and deleting it raises no error
    anywhere, so the recorded mtime is re-checked at the last opportunity."""
    nm = tmp_path / "node_modules"
    (nm / "dep").mkdir(parents=True)
    scanned_at = os.path.getmtime(nm)
    items = [{"path": str(nm), "size_bytes": 10, "label": "node_modules",
              "meta": {"mtime": scanned_at}}]
    (nm / "arrived-after-the-scan").write_text("x")

    with patch("cleaner.send2trash") as mock_trash:
        result = clean_items(items, permanent=False)

    mock_trash.assert_not_called()
    assert nm.exists()
    assert result.skipped == 1
    assert result.moved == 0
    assert result.errors == 0


def test_an_untouched_directory_is_still_cleaned(tmp_path):
    """The control: the re-check must not refuse everything."""
    nm = tmp_path / "node_modules"
    (nm / "dep").mkdir(parents=True)
    items = [{"path": str(nm), "size_bytes": 10, "label": "node_modules",
              "meta": {"mtime": os.path.getmtime(nm)}}]

    with patch("cleaner.send2trash") as mock_trash:
        result = clean_items(items, permanent=False)

    mock_trash.assert_called_once_with(str(nm))
    assert result.moved == 1
    assert result.skipped == 0


def test_a_change_deep_inside_is_not_detected_and_that_is_the_documented_limit(tmp_path):
    """Pinned so the limit is stated rather than assumed: a directory's mtime
    moves when an entry is added or removed in it, not when a file three levels
    down is rewritten. The re-check catches an install; the dormancy rule in
    dev_junk is what catches a project still being worked on."""
    nm = tmp_path / "node_modules"
    deep = nm / "pkg" / "lib"
    deep.mkdir(parents=True)
    (deep / "index.js").write_text("original")
    items = [{"path": str(nm), "size_bytes": 10, "label": "node_modules",
              "meta": {"mtime": os.path.getmtime(nm)}}]
    (deep / "index.js").write_text("rewritten in place")

    with patch("cleaner.send2trash") as mock_trash:
        result = clean_items(items, permanent=False)

    mock_trash.assert_called_once_with(str(nm))
    assert result.moved == 1
    assert result.changed_paths == []


def test_a_changed_directory_is_named_not_just_counted(tmp_path):
    """The report says 'duplicate or already-covered' for an ordinary skip; a
    path left alone because it changed is a different thing and has to read
    like one."""
    nm = tmp_path / "node_modules"
    (nm / "dep").mkdir(parents=True)
    items = [{"path": str(nm), "size_bytes": 10, "label": "node_modules",
              "meta": {"mtime": os.path.getmtime(nm)}}]
    (nm / "new").write_text("x")

    with patch("cleaner.send2trash"):
        result = clean_items(items, permanent=False)

    assert result.changed_paths == [str(nm)]
