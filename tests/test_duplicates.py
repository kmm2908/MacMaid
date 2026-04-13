import os
from unittest.mock import patch
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
