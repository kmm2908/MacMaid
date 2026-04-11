import os
import time
from unittest.mock import patch
from modules.large_files import scan

def test_finds_large_file(tmp_path):
    big = tmp_path / "big.zip"
    big.write_bytes(b"x" * (600 * 1024 * 1024))  # 600 MB

    with patch("modules.large_files.SCAN_PATHS", [str(tmp_path)]), \
         patch("modules.large_files.THRESHOLD_BYTES", 500 * 1024 * 1024), \
         patch("modules.large_files.OLD_FILE_SECONDS", 180 * 86400):
        result = scan()

    assert any("big.zip" in i["label"] for i in result["items"])
    assert result["risk"] == "review"

def test_finds_old_file(tmp_path):
    old = tmp_path / "old.dmg"
    old.write_bytes(b"x" * 1024)
    old_time = time.time() - (200 * 86400)
    os.utime(str(old), (old_time, old_time))

    with patch("modules.large_files.SCAN_PATHS", [str(tmp_path)]), \
         patch("modules.large_files.THRESHOLD_BYTES", 500 * 1024 * 1024), \
         patch("modules.large_files.OLD_FILE_SECONDS", 180 * 86400):
        result = scan()

    assert any("old.dmg" in i["label"] for i in result["items"])

def test_ignores_small_recent_files(tmp_path):
    small = tmp_path / "small.txt"
    small.write_text("hello")

    with patch("modules.large_files.SCAN_PATHS", [str(tmp_path)]), \
         patch("modules.large_files.THRESHOLD_BYTES", 500 * 1024 * 1024), \
         patch("modules.large_files.OLD_FILE_SECONDS", 180 * 86400):
        result = scan()

    assert not any("small.txt" in i["label"] for i in result["items"])
