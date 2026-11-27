import os
import plistlib
import subprocess
import time
from unittest.mock import patch

import pytest

import cleaner
import config
import main
from modules import downloads

OLD = time.time() - 3 * 86400


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    with patch.object(downloads, "DOWNLOADS", str(folder)):
        yield folder


def _file(path, mtime=OLD):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    os.utime(path, (mtime, mtime))
    return path


def _tag(path, name="Red\n6"):
    data = plistlib.dumps([name], fmt=plistlib.FMT_BINARY).hex()
    subprocess.run(["xattr", "-w", "-x", downloads.TAG_ATTR, data, str(path)], check=True)


def _paths(result):
    return [i["path"] for i in result["items"]]


def _clean(result):
    # permanent=True keeps the test files out of the real Trash
    items = [{**i, "action": result["action"]} for i in result["items"]]
    return cleaner.clean_items(items, permanent=True)


def test_offers_old_files_and_keeps_recent_ones(root):
    old = _file(root / "old.zip")
    _file(root / "new.zip", mtime=time.time())
    result = downloads.scan()
    assert result["risk"] == "safe" and result["action"] == "trash"
    assert _paths(result) == [str(old)]
    assert "1 recent" in result["suggestion"]


def test_red_tag_protects_a_file_and_a_whole_subtree(root):
    _tag(_file(root / "keep.pdf"))
    inside = _file(root / "project" / "deep" / "a.txt")
    _tag(inside.parent.parent)
    result = downloads.scan()
    assert result["items"] == []
    assert "2 red-tagged" in result["suggestion"]


def test_another_colour_tag_does_not_protect(root):
    blue = _file(root / "blue.pdf")
    _tag(blue, "Blue\n4")
    assert _paths(downloads.scan()) == [str(blue)]


def test_unreadable_tags_protect_the_file(root):
    _file(root / "a.pdf")
    failed = subprocess.CompletedProcess([], 1, "", "xattr: Operation not permitted")
    with patch.object(downloads.subprocess, "run", return_value=failed):
        assert downloads.scan()["items"] == []


def test_symlinks_are_left_alone(root, tmp_path):
    target = _file(tmp_path / "outside" / "real.txt")
    (root / "link.txt").symlink_to(target)
    (root / "linkdir").symlink_to(target.parent)
    assert downloads.scan()["items"] == []


def test_emptied_folders_follow_their_files_deepest_first(root):
    f = _file(root / "a" / "b" / "c.txt")
    result = downloads.scan()
    assert _paths(result) == [str(f), str(f.parent), str(f.parent.parent)]
    assert _clean(result).moved == 3
    assert root.exists() and not (root / "a").exists()


def test_folder_holding_a_recent_file_is_not_offered(root):
    old = _file(root / "a" / "old.txt")
    _file(root / "a" / "new.txt", mtime=time.time())
    assert _paths(downloads.scan()) == [str(old)]


def test_folder_filled_after_the_scan_is_left_alone(root):
    _file(root / "a" / "old.txt")
    result = downloads.scan()
    arrived = _file(root / "a" / "arrived.txt", mtime=time.time())
    cleaned = _clean(result)
    assert arrived.exists()
    assert cleaned.changed_paths == [str(root / "a")]


def test_file_rewritten_after_the_scan_is_left_alone(root):
    f = _file(root / "a.txt")
    result = downloads.scan()
    os.utime(f, None)
    assert _clean(result).moved == 0 and f.exists()


@pytest.mark.parametrize("tag_parent", [False, True])
def test_red_tag_added_after_the_scan_is_honoured(root, tag_parent):
    f = _file(root / "a" / "b.txt")
    result = downloads.scan()
    _tag(f.parent if tag_parent else f)
    _clean(result)
    assert f.exists()


def test_unreadable_downloads_is_reported_not_read_as_clean(root):
    with patch.object(downloads, "DOWNLOADS", str(root / "missing")):
        result = downloads.scan()
    assert result["items"] == []
    assert "Could not read 1 item" in result["suggestion"]


def test_off_until_switched_on(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.module_enabled("downloads") is False
    cfg_file.write_text('{"modules": {"downloads": true}}')
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.module_enabled("downloads") is True
    config._reset()


def test_runs_after_the_trash_is_emptied():
    """Moved files keep their old mtime, so emptying afterwards would delete them at once."""
    names = list(main.MODULES)
    assert names.index("downloads") > names.index("trash")


def test_file_arriving_during_folder_removal_survives(root):
    _file(root / "a" / "old.txt")
    result = downloads.scan()
    late = root / "a" / "late.txt"
    real_listdir = os.listdir

    def listdir_then_a_file_arrives(path):
        names = real_listdir(path)
        _file(late)
        return names

    with patch.object(cleaner.os, "listdir", listdir_then_a_file_arrives):
        cleaned = _clean(result)
    assert late.exists()
    assert cleaned.changed_paths == [str(root / "a")]


def test_folder_with_only_finder_metadata_is_removed(root):
    _file(root / "a" / ".DS_Store", mtime=time.time())
    assert _clean(downloads.scan()).errors == 0
    assert not (root / "a").exists()


def test_emptied_folder_does_not_swallow_a_later_candidate():
    folder = {"path": "/x/a", "meta": {"only_if_empty": True}}
    nested = {"path": "/x/a/b", "meta": {}}
    assert cleaner.plan_items([folder, nested])[0] == [folder, nested]


def test_unreadable_file_is_counted(root):
    f = _file(root / "a.txt")
    real_stat = os.stat

    def refuse(path, *args, **kwargs):
        if path == str(f):
            raise PermissionError(path)
        return real_stat(path, *args, **kwargs)

    with patch.object(downloads.os, "stat", refuse), \
         patch.object(downloads.os.path, "islink", return_value=False):
        assert "Could not read 1 item" in downloads.scan()["suggestion"]


def test_nightly_review_list_drops_what_was_auto_cleaned(tmp_path):
    moved = {"path": "/x/big.iso", "size_bytes": 5, "label": "big", "meta": {}}
    stays = {"path": "/x/other.iso", "size_bytes": 7, "label": "other", "meta": {}}
    results = [{"category": "Large & Old Files", "risk": "review", "action": "trash",
                "suggestion": "", "items": [moved, stays], "total_size_bytes": 12}]
    done = cleaner.CleanResult(moved=1, moved_paths=[moved["path"]])
    with patch.object(main.cleaner_mod, "clean_items", return_value=done), \
         patch.object(main, "save_results") as saved, \
         patch.object(main.history, "record"), \
         patch.object(main, "log_errors"):
        main.unattended_mode(results, False, "", no_email=True)
    kept = saved.call_args.args[0][0]
    assert kept["items"] == [stays] and kept["total_size_bytes"] == 7
