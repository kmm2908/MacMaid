"""Mail and device backups are left alone if anything inside changed since the scan."""
import json
import os
from unittest.mock import patch

import cleaner
from modules import ios_backups, mail

FUTURE = 1_900_000_000  # 2030: the newest mtime in the tree, whatever happens later
PAST = 1_700_000_000


def _mail_with_a_future_dated_file(tmp_path):
    root = tmp_path / "Mail"
    (root / "V10").mkdir(parents=True)
    for name, when in (("future.emlx", FUTURE), ("old.emlx", PAST)):
        (root / "V10" / name).write_bytes(b"x" * 100)
        os.utime(root / "V10" / name, (when, when))
    return root


def _scanned_item(root):
    with patch.object(mail, "MAIL_DIR", str(root)):
        result = mail.scan()
    # The review page cleans what it reads back from the saved results.
    return {**json.loads(json.dumps(result["items"][0])), "action": "trash"}


def _clean(item):
    with patch("cleaner.send2trash") as bin_it:
        return cleaner.clean_items([item]), bin_it


def test_an_untouched_tree_is_still_cleaned(tmp_path):
    item = _scanned_item(_mail_with_a_future_dated_file(tmp_path))
    result, bin_it = _clean(item)
    bin_it.assert_called_once_with(item["path"])
    assert result.moved == 1


def test_a_change_behind_a_future_dated_file_is_seen(tmp_path):
    root = _mail_with_a_future_dated_file(tmp_path)
    item = _scanned_item(root)
    os.utime(root / "V10" / "old.emlx", (PAST + 3600, PAST + 3600))
    result, bin_it = _clean(item)
    bin_it.assert_not_called()
    assert result.changed_paths == [str(root)]


def test_a_tree_that_can_no_longer_be_read_is_left_alone(tmp_path):
    root = _mail_with_a_future_dated_file(tmp_path)
    item = _scanned_item(root)
    (root / "V10").chmod(0)
    try:
        result, bin_it = _clean(item)
    finally:
        (root / "V10").chmod(0o755)
    bin_it.assert_not_called()
    assert result.changed_paths == [str(root)]


def test_results_saved_with_only_the_newest_mtime_are_left_alone(tmp_path):
    root = _mail_with_a_future_dated_file(tmp_path)
    item = {"path": str(root), "size_bytes": 200, "label": "Mail", "action": "trash",
            "meta": {"tree_mtime": float(FUTURE)}}
    result, bin_it = _clean(item)
    bin_it.assert_not_called()
    assert result.changed_paths == [str(root)]


def test_a_mail_store_that_cannot_be_fully_read_is_not_offered_and_says_so(tmp_path):
    root = _mail_with_a_future_dated_file(tmp_path)
    (root / "locked").mkdir()
    (root / "locked").chmod(0)
    try:
        with patch.object(mail, "MAIL_DIR", str(root)):
            result = mail.scan()
    finally:
        (root / "locked").chmod(0o755)
    assert result["items"] == []
    assert "could not be read" in result["suggestion"]


def test_a_backup_that_cannot_be_fully_read_is_not_offered_and_is_counted(tmp_path):
    for name in ("good", "bad"):
        (tmp_path / name / "inner").mkdir(parents=True)
        (tmp_path / name / "inner" / "Manifest.db").write_bytes(b"x" * 100)
    (tmp_path / "bad" / "inner").chmod(0)
    try:
        with patch.object(ios_backups, "BACKUP_DIR", str(tmp_path)):
            result = ios_backups.scan()
    finally:
        (tmp_path / "bad" / "inner").chmod(0o755)
    assert [i["path"] for i in result["items"]] == [str(tmp_path / "good")]
    assert "1 backup(s) could not be read" in result["suggestion"]


def test_a_same_size_rewrite_with_the_old_time_put_back_is_seen(tmp_path):
    root = _mail_with_a_future_dated_file(tmp_path)
    item = _scanned_item(root)
    (root / "V10" / "old.emlx").write_bytes(b"y" * 100)
    os.utime(root / "V10" / "old.emlx", (PAST, PAST))
    result, bin_it = _clean(item)
    bin_it.assert_not_called()
    assert result.changed_paths == [str(root)]


def test_a_backup_folder_that_cannot_be_listed_says_so(tmp_path):
    tmp_path.joinpath("Backup").mkdir(mode=0)
    try:
        with patch.object(ios_backups, "BACKUP_DIR", str(tmp_path / "Backup")):
            result = ios_backups.scan()
    finally:
        tmp_path.joinpath("Backup").chmod(0o755)
    assert result["items"] == []
    assert "could not be read" in result["suggestion"]
    assert "0 backup(s)" not in result["suggestion"]


def test_an_unencodable_path_is_still_written_to_the_error_log(tmp_path):
    log = tmp_path / "error.log"
    with patch.object(cleaner, "ERROR_LOG_PATH", log):
        cleaner.log_errors(cleaner.CleanResult(errors=1, error_paths=[("/bad/\udcff", "refused")]))
    assert "refused" in log.read_text()


def test_a_file_added_to_a_folder_already_read_is_not_missed(tmp_path):
    root = _mail_with_a_future_dated_file(tmp_path)
    item = _scanned_item(root)
    real_walk, added = os.walk, []

    def walk_then_deliver(top, **kwargs):
        for step in real_walk(top, **kwargs):
            yield step
            if step[0].endswith("V10") and not added:  # that folder has now been read
                (root / "V10" / "new.emlx").write_bytes(b"new mail")
                added.append(True)

    with patch("os.walk", walk_then_deliver):
        result, bin_it = _clean(item)
    assert added
    bin_it.assert_not_called()
    assert result.changed_paths == [str(root)]
