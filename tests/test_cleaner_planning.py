import os
import time

from cleaner import clean_items, plan_items, empty_trash


def _item(path, size=10, action="trash"):
    return {"path": path, "size_bytes": size, "label": os.path.basename(path),
            "meta": {}, "action": action}


# ---------- plan_items: drop work that is guaranteed to fail ----------

def test_plan_drops_exact_duplicate_paths():
    # browsers and caches both list ~/Library/Caches/com.apple.Safari
    items = [_item("/a/Safari"), _item("/a/Safari")]
    kept, dropped = plan_items(items)
    assert [i["path"] for i in kept] == ["/a/Safari"]
    assert dropped == 1


def test_plan_drops_paths_nested_under_an_earlier_candidate():
    # trashing /a removes /a/b, so cleaning /a/b afterwards is a certain error
    items = [_item("/a"), _item("/a/b"), _item("/a/b/c")]
    kept, dropped = plan_items(items)
    assert [i["path"] for i in kept] == ["/a"]
    assert dropped == 2


def test_plan_keeps_siblings_and_lookalike_prefixes():
    items = [_item("/a/one"), _item("/a/two"), _item("/a/onetwo")]
    kept, _ = plan_items(items)
    assert len(kept) == 3


def test_plan_is_pure_and_does_not_mutate_input():
    items = [_item("/a"), _item("/a/b")]
    before = [dict(i) for i in items]
    plan_items(items)
    assert items == before


def test_plan_keeps_child_when_parent_is_a_different_action():
    # ~/.Trash is emptied, not trashed, so entries under it are not implied gone
    items = [_item("/t", action="empty-trash"), _item("/t/x")]
    kept, _ = plan_items(items)
    assert len(kept) == 2


# ---------- empty_trash: the action that was never implemented ----------

def _age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_empty_trash_removes_entries_older_than_retention(tmp_path):
    old = tmp_path / "old.txt"
    old.write_text("x" * 100)
    _age(old, 30)
    removed, freed, errors = empty_trash(str(tmp_path), older_than_days=7)
    assert not old.exists()
    assert removed == 1
    assert freed == 100
    assert errors == 0


def test_empty_trash_keeps_recent_entries(tmp_path):
    recent = tmp_path / "recent.txt"
    recent.write_text("x" * 50)
    _age(recent, 2)
    removed, freed, errors = empty_trash(str(tmp_path), older_than_days=7)
    assert recent.exists()
    assert removed == 0
    assert freed == 0


def test_empty_trash_removes_old_directories_recursively(tmp_path):
    d = tmp_path / "old-project"
    (d / "nested").mkdir(parents=True)
    (d / "nested" / "f.bin").write_text("x" * 20)
    _age(d, 60)
    removed, freed, errors = empty_trash(str(tmp_path), older_than_days=7)
    assert not d.exists()
    assert removed == 1
    assert freed == 20


def test_empty_trash_keeps_the_trash_folder_itself(tmp_path):
    old = tmp_path / "old.txt"
    old.write_text("x")
    _age(old, 30)
    empty_trash(str(tmp_path), older_than_days=7)
    assert tmp_path.is_dir()


def test_empty_trash_missing_dir_is_not_an_error():
    removed, freed, errors = empty_trash("/nonexistent/trash", older_than_days=7)
    assert (removed, freed, errors) == (0, 0, 0)


# ---------- clean_items dispatches on action ----------

def test_clean_items_routes_empty_trash_action(tmp_path):
    old = tmp_path / "old.txt"
    old.write_text("x" * 10)
    _age(old, 30)
    items = [_item(str(tmp_path), size=10, action="empty-trash")]
    result = clean_items(items, permanent=False, trash_retention_days=7)
    assert not old.exists()
    assert tmp_path.is_dir()
    assert result.errors == 0
    assert result.moved == 1
    assert result.bytes_freed == 10


def test_clean_items_does_not_send_trash_folder_to_trash(tmp_path):
    """The original bug: send2trash(~/.Trash) — trashing the Trash."""
    items = [_item(str(tmp_path), action="empty-trash")]
    from unittest.mock import patch
    with patch("cleaner.send2trash") as mock_trash:
        clean_items(items, permanent=False, trash_retention_days=7)
    mock_trash.assert_not_called()


def test_clean_items_counts_deduped_work_as_skipped(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    items = [_item(str(f)), _item(str(f))]
    from unittest.mock import patch
    with patch("cleaner.send2trash"):
        result = clean_items(items, permanent=False)
    assert result.moved == 1
    assert result.errors == 0
    assert result.skipped == 1
