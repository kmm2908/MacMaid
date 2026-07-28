import os
import time

from modules import trash


def _age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


def test_trash_dirs_includes_home_trash():
    assert os.path.expanduser("~/.Trash") in trash.trash_dirs()


def test_trash_dirs_includes_mounted_volume_trashes(tmp_path, monkeypatch):
    vol = tmp_path / "Ext Data" / ".Trashes" / str(os.getuid())
    vol.mkdir(parents=True)
    monkeypatch.setattr(trash, "VOLUMES_DIR", str(tmp_path))
    assert str(vol) in trash.trash_dirs()


def test_trash_dirs_skips_volumes_without_a_user_trash(tmp_path, monkeypatch):
    (tmp_path / "Some Disk").mkdir(parents=True)
    monkeypatch.setattr(trash, "VOLUMES_DIR", str(tmp_path))
    assert not any("Some Disk" in d for d in trash.trash_dirs())


def test_reclaimable_size_counts_only_entries_past_retention(tmp_path):
    old = tmp_path / "old.bin"
    old.write_text("x" * 100)
    _age(old, 30)
    recent = tmp_path / "recent.bin"
    recent.write_text("x" * 500)
    _age(recent, 1)
    assert trash.reclaimable_size(str(tmp_path), older_than_days=7) == 100


def test_scan_reports_one_item_per_trash_with_reclaimable_content(tmp_path, monkeypatch):
    home = tmp_path / "home-trash"
    home.mkdir()
    old = home / "old.bin"
    old.write_text("x" * 42)
    _age(old, 30)

    empty = tmp_path / "empty-trash"
    empty.mkdir()

    monkeypatch.setattr(trash, "trash_dirs", lambda: [str(home), str(empty)])
    result = trash.scan()

    assert result["action"] == "empty-trash"
    assert result["risk"] == "safe"
    assert [i["path"] for i in result["items"]] == [str(home)]
    assert result["total_size_bytes"] == 42


def test_scan_with_nothing_old_enough_returns_no_items(tmp_path, monkeypatch):
    d = tmp_path / "t"
    d.mkdir()
    recent = d / "recent.bin"
    recent.write_text("x" * 10)
    _age(recent, 1)
    monkeypatch.setattr(trash, "trash_dirs", lambda: [str(d)])
    result = trash.scan()
    assert result["items"] == []
