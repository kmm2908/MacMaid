"""The retention window counts from when an item was binned, not last edited."""
import os
import time

import cleaner
from cleaner import empty_trash
from modules import base, trash

DAY = 86400


def _old(path, days=30):
    t = time.time() - days * DAY
    os.utime(path, (t, t))


def _bin_old_file(tmp_path):
    """A file last edited a month ago, moved into the Trash just now."""
    source = tmp_path / "report.pdf"
    source.write_bytes(b"x" * 100)
    _old(source)
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    binned = trash_dir / source.name
    os.rename(source, binned)
    return trash_dir, binned


def test_an_old_file_binned_today_is_not_emptied(tmp_path):
    trash_dir, binned = _bin_old_file(tmp_path)

    assert empty_trash(str(trash_dir), older_than_days=7) == (0, 0, 0)
    assert binned.exists()


def test_an_old_file_binned_today_is_not_reported_as_reclaimable(tmp_path):
    trash_dir, _ = _bin_old_file(tmp_path)

    assert trash.reclaimable_size(str(trash_dir), older_than_days=7) == 0


def test_added_time_is_when_the_item_was_moved_in(tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"x")
    (tmp_path / "trash").mkdir()
    time.sleep(0.2)
    moved_at = time.time()
    binned = tmp_path / "trash" / source.name
    os.rename(source, binned)

    # later than the move, so neither creation nor modification time can pass
    assert moved_at - 0.05 <= base.added_time(str(binned)) <= time.time() + 0.05


def test_added_time_of_a_missing_path_is_unknown(tmp_path):
    assert base.added_time(str(tmp_path / "gone")) is None


def test_an_item_with_no_known_binned_time_is_kept(tmp_path, monkeypatch):
    trash_dir, binned = _bin_old_file(tmp_path)
    monkeypatch.setattr(base, "added_time", lambda path: None)

    assert trash.reclaimable_size(str(trash_dir), older_than_days=7) == 0
    assert empty_trash(str(trash_dir), older_than_days=7) == (0, 0, 0)
    assert binned.exists()


def test_an_item_binned_long_ago_is_emptied(tmp_path, monkeypatch):
    trash_dir, binned = _bin_old_file(tmp_path)
    monkeypatch.setattr(base, "added_time", lambda path: time.time() - 8 * DAY)

    assert trash.reclaimable_size(str(trash_dir), older_than_days=7) == 100
    assert empty_trash(str(trash_dir), older_than_days=7) == (1, 100, 0)
    assert not binned.exists()


def test_something_written_after_it_was_binned_is_still_kept(tmp_path, monkeypatch):
    trash_dir, binned = _bin_old_file(tmp_path)
    os.utime(binned)
    monkeypatch.setattr(base, "added_time", lambda path: time.time() - 8 * DAY)

    assert empty_trash(str(trash_dir), older_than_days=7) == (0, 0, 0)
    assert binned.exists()


def test_a_hard_linked_file_is_kept(tmp_path, monkeypatch):
    """Apple documents Date Added as unreliable for hard links."""
    trash_dir, binned = _bin_old_file(tmp_path)
    os.link(binned, tmp_path / "other-name")
    monkeypatch.setattr(base, "added_time", lambda path: time.time() - 8 * DAY)

    assert empty_trash(str(trash_dir), older_than_days=7) == (0, 0, 0)
    assert binned.exists()


def _binned_folder(tmp_path, monkeypatch):
    """A folder binned 8 days ago whose contents are all a month old."""
    folder = tmp_path / "trash" / "project"
    deep = folder / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "notes.txt").write_bytes(b"x" * 5)
    for path in [deep / "notes.txt", deep, deep.parent, folder]:
        _old(path)
    monkeypatch.setattr(base, "added_time", lambda path: time.time() - 8 * DAY)
    return folder, deep / "notes.txt"


def test_an_untouched_binned_folder_is_emptied(tmp_path, monkeypatch):
    folder, _ = _binned_folder(tmp_path, monkeypatch)

    assert empty_trash(str(folder.parent), older_than_days=7) == (1, 5, 0)
    assert not folder.exists()


def test_a_folder_written_to_deep_inside_is_kept(tmp_path, monkeypatch):
    folder, nested = _binned_folder(tmp_path, monkeypatch)
    os.utime(nested)

    assert trash.reclaimable_size(str(folder.parent), older_than_days=7) == 0
    assert empty_trash(str(folder.parent), older_than_days=7) == (0, 0, 0)
    assert nested.exists()


def test_a_symlink_is_judged_on_itself_not_its_target(tmp_path, monkeypatch):
    target = tmp_path / "live"
    target.mkdir()
    (target / "fresh.txt").write_bytes(b"x")
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    link = trash_dir / "link"
    link.symlink_to(target)
    t = time.time() - 30 * DAY
    os.utime(link, (t, t), follow_symlinks=False)
    monkeypatch.setattr(base, "added_time", lambda path: time.time() - 8 * DAY)

    assert empty_trash(str(trash_dir), older_than_days=7)[0] == 1
    assert (target / "fresh.txt").exists()


def test_a_write_while_the_entry_is_being_sized_keeps_it(tmp_path, monkeypatch):
    folder, nested = _binned_folder(tmp_path, monkeypatch)
    real_size = cleaner._entry_size

    def size_then_write(path):
        size = real_size(path)
        os.utime(nested)
        return size

    monkeypatch.setattr(cleaner, "_entry_size", size_then_write)

    assert empty_trash(str(folder.parent), older_than_days=7) == (0, 0, 0)
    assert nested.exists()


def test_a_folder_that_cannot_be_fully_read_is_kept_and_counted(tmp_path, monkeypatch):
    folder, nested = _binned_folder(tmp_path, monkeypatch)
    sibling = folder / "keep.txt"
    sibling.write_bytes(b"x" * 3)
    _old(sibling)
    _old(folder)
    locked = nested.parent
    locked.chmod(0)
    try:
        assert trash.reclaimable_size(str(folder.parent), older_than_days=7) == 0
        assert empty_trash(str(folder.parent), older_than_days=7) == (0, 0, 1)
        assert sibling.exists()
    finally:
        locked.chmod(0o755)
    assert nested.exists()


def test_date_added_moves_forward_when_a_backdated_folder_is_binned(tmp_path):
    """Probed 2026-11-27 on the boot volume and an external one: a rename into
    another folder (which is what send2trash's trashItemAtURL does on one volume)
    sets Date Added to the move, whatever the item's mtime says."""
    import shutil

    source = tmp_path / "old folder"
    source.mkdir()
    (source / "a.txt").write_text("x")
    for p in (source / "a.txt", source):
        _old(p)
    (tmp_path / "trash").mkdir()
    time.sleep(0.2)
    moved_at = time.time()
    binned = tmp_path / "trash" / source.name
    shutil.move(str(source), str(binned))

    assert base.added_time(str(binned)) >= moved_at - 0.05
    assert not base.binned_before(str(binned), time.time() - 7 * DAY)
    assert empty_trash(str(tmp_path / "trash"), older_than_days=7) == (0, 0, 0)
    assert binned.exists()
