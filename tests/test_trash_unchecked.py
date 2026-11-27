"""The Trash scan must say what it could not check, not count it as nothing old."""
import os
import time
from unittest.mock import patch

import pytest

from modules import base, trash

DAY = 86400


def _scan(*dirs):
    with patch.object(trash, "trash_dirs", return_value=[str(d) for d in dirs]), \
         patch.object(trash, "TRASH_PATH", str(dirs[0])), \
         patch.object(trash.cfg, "get", return_value=7):
        return trash.scan()


def _old_file(path, size=100):
    path.write_bytes(b"x" * size)
    then = time.time() - 30 * DAY
    os.utime(path, (then, then))
    return path


@pytest.fixture
def trash_dir(tmp_path):
    folder = tmp_path / ".Trash"
    folder.mkdir()
    return folder


@pytest.fixture
def locked():
    """Take away all access to a folder, and give it back so pytest can clean up."""
    folders = []

    def lock(folder):
        os.chmod(folder, 0)
        folders.append(folder)

    yield lock
    for folder in folders:
        os.chmod(folder, 0o700)


def test_unlistable_trash_is_reported(trash_dir, locked):
    locked(trash_dir)
    suggestion = _scan(trash_dir)["suggestion"]
    assert "could not check: Trash (could not be opened)" in suggestion
    assert "Nothing has been in the Trash" not in suggestion


def test_entries_with_no_binned_date_are_counted(trash_dir, monkeypatch):
    monkeypatch.setattr(base, "added_time", lambda path: None)
    _old_file(trash_dir / "a")
    _old_file(trash_dir / "b")
    suggestion = _scan(trash_dir)["suggestion"]
    assert "could not check: 2 item(s)" in suggestion
    assert "Nothing has been in the Trash" not in suggestion


def test_hard_linked_file_is_counted_as_unchecked(trash_dir, tmp_path, binned_when_modified):
    os.link(_old_file(tmp_path / "original"), trash_dir / "linked")
    assert "could not check: 1 item(s)" in _scan(trash_dir)["suggestion"]


def test_partly_unreadable_folder_is_counted(trash_dir, locked, binned_when_modified):
    entry = trash_dir / "folder"
    inner = entry / "inner"
    inner.mkdir(parents=True)
    locked(inner)
    then = time.time() - 30 * DAY
    os.utime(entry, (then, then))
    assert "could not check: 1 item(s)" in _scan(trash_dir)["suggestion"]


def test_unchecked_is_reported_beside_what_can_be_emptied(trash_dir, tmp_path, locked,
                                                          binned_when_modified):
    _old_file(trash_dir / "old")
    other = tmp_path / "other"
    other.mkdir()
    locked(other)
    result = _scan(trash_dir, other)
    assert result["total_size_bytes"] == 100
    assert result["suggestion"].startswith("Permanently free")
    assert "Could not check: " in result["suggestion"]


def test_fully_checked_trash_mentions_nothing_unchecked(trash_dir, binned_when_modified):
    (trash_dir / "recent").write_bytes(b"x")
    assert _scan(trash_dir)["suggestion"] == "Nothing has been in the Trash longer than 7 days"


def test_missing_trash_folder_is_not_unchecked(tmp_path):
    assert "check" not in _scan(tmp_path / "absent")["suggestion"]


def test_entry_that_vanishes_during_the_scan_is_not_unchecked(trash_dir):
    with patch.object(trash.os, "listdir", return_value=["gone"]):
        assert "check" not in _scan(trash_dir)["suggestion"]


@pytest.mark.parametrize("failing", ["walk", "getsize"])
def test_entry_that_fails_while_being_sized_is_counted_once(trash_dir, monkeypatch,
                                                            binned_when_modified, failing):
    entry = trash_dir / "folder"
    entry.mkdir()
    _old_file(entry / "a")
    _old_file(entry / "b")
    then = time.time() - 30 * DAY
    os.utime(entry, (then, then))
    denied = PermissionError("denied")

    def broken_walk(path, onerror=None):
        if onerror:
            onerror(denied)
        return iter([])

    def broken_getsize(path):
        raise denied

    # let the age check pass, then fail only the sizing
    monkeypatch.setattr(trash, "binned_before", lambda path, cutoff: True)
    if failing == "walk":
        monkeypatch.setattr(trash.os, "walk", broken_walk)
    else:
        monkeypatch.setattr(trash.os.path, "getsize", broken_getsize)
    assert "could not check: 1 item(s)" in _scan(trash_dir)["suggestion"]


def test_unlistable_volumes_folder_is_reported(trash_dir, tmp_path, locked, monkeypatch):
    volumes = tmp_path / "Volumes"
    volumes.mkdir()
    locked(volumes)
    monkeypatch.setattr(trash, "TRASH_PATH", str(trash_dir))
    monkeypatch.setattr(trash, "VOLUMES_DIR", str(volumes))
    suggestion = trash.scan()["suggestion"]
    assert "could not check: Trash on other volumes (could not be listed)" in suggestion


def test_volume_trash_that_cannot_be_reached_is_reported(trash_dir, tmp_path, locked, monkeypatch):
    volumes = tmp_path / "Volumes"
    trashes = volumes / "Backup" / ".Trashes"
    (trashes / str(os.getuid())).mkdir(parents=True)
    locked(trashes)
    monkeypatch.setattr(trash, "TRASH_PATH", str(trash_dir))
    monkeypatch.setattr(trash, "VOLUMES_DIR", str(volumes))
    monkeypatch.setattr(trash, "_label", lambda path: "Trash" if path == str(trash_dir) else "volume")
    assert "could not check: volume (could not be opened)" in trash.scan()["suggestion"]
