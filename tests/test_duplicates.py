import os
from unittest.mock import patch

import pytest

import cleaner
from modules.duplicates import scan


def test_finds_duplicate_files(tmp_path):
    content = b"identical content here"
    f1 = tmp_path / "file1.pdf"
    f2 = tmp_path / "file1_copy.pdf"
    f3 = tmp_path / "different.pdf"
    f1.write_bytes(content)
    f2.write_bytes(content)
    f3.write_bytes(b"different content")

    with patch("modules.duplicates.cfg.get", return_value=[str(tmp_path)]):
        result = scan()

    assert result["category"] == "Duplicates"
    assert result["risk"] == "review"
    dup_paths = [i["path"] for i in result["items"]]
    assert len(dup_paths) >= 1

def test_no_duplicates(tmp_path):
    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bbb")

    with patch("modules.duplicates.cfg.get", return_value=[str(tmp_path)]):
        result = scan()

    assert result["items"] == []
    assert result["total_size_bytes"] == 0

def test_empty_directory(tmp_path):
    with patch("modules.duplicates.cfg.get", return_value=[str(tmp_path)]):
        result = scan()
    assert result["items"] == []


def _scan_over(*paths):
    with patch("modules.duplicates.cfg.get", return_value=[str(p) for p in paths]):
        return scan()["items"]


def test_overlapping_scan_paths_do_not_flag_a_file_as_its_own_duplicate(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "only.txt").write_text("the only copy")

    assert _scan_over(tmp_path, tmp_path / "sub") == []


def test_symlink_does_not_make_its_target_a_duplicate(tmp_path):
    (tmp_path / "only.txt").write_text("the only copy")
    os.symlink(tmp_path / "only.txt", tmp_path / "link.txt")

    assert _scan_over(tmp_path) == []


def test_hard_link_is_not_a_duplicate(tmp_path):
    (tmp_path / "only.txt").write_text("the only copy")
    os.link(tmp_path / "only.txt", tmp_path / "hard.txt")

    assert _scan_over(tmp_path) == []


def test_hard_linked_file_is_kept_and_the_independent_copy_offered(tmp_path):
    (tmp_path / "linked.txt").write_text("same bytes")
    os.link(tmp_path / "linked.txt", tmp_path / "linked2.txt")
    (tmp_path / "copy.txt").write_text("same bytes")
    os.utime(tmp_path / "linked.txt", (1, 1))  # older than the copy

    assert [i["label"] for i in _scan_over(tmp_path)] == ["copy.txt"]


def test_symlink_to_a_file_outside_the_scan_is_not_a_copy(tmp_path):
    (tmp_path / "scan").mkdir()
    (tmp_path / "outside.txt").write_text("same bytes")
    (tmp_path / "scan" / "real.txt").write_text("same bytes")
    os.symlink(tmp_path / "outside.txt", tmp_path / "scan" / "link.txt")

    assert _scan_over(tmp_path / "scan") == []


@pytest.mark.parametrize("spoil", [lambda keeper: keeper.unlink(),
                                   lambda keeper: keeper.write_text("edited since"),
                                   lambda keeper: (keeper.unlink(),
                                                   keeper.symlink_to(keeper.with_name("copy.txt")))])
def test_duplicate_is_not_trashed_once_its_keeper_is_gone_or_changed(tmp_path, spoil):
    (tmp_path / "keep.txt").write_text("same bytes")
    (tmp_path / "copy.txt").write_text("same bytes")
    os.utime(tmp_path / "copy.txt", (1, 1))
    items = _scan_over(tmp_path)
    spoil(tmp_path / "keep.txt")

    with patch("cleaner.send2trash") as trash:
        result = cleaner.clean_items(items)

    trash.assert_not_called()
    assert result.moved == 0
    assert "kept:" in result.error_paths[0][1]
    assert "not found" not in result.error_paths[0][1].lower()  # the review page drops those rows


def test_duplicate_with_an_intact_keeper_is_trashed(tmp_path):
    (tmp_path / "keep.txt").write_text("same bytes")
    (tmp_path / "copy.txt").write_text("same bytes")

    with patch("cleaner.send2trash") as trash:
        assert cleaner.clean_items(_scan_over(tmp_path)).moved == 1

    trash.assert_called_once()
