from io import StringIO
from unittest.mock import patch
from reporter import format_size, build_summary_text

def test_format_size_bytes():
    assert format_size(512) == "512 B"

def test_format_size_mb():
    assert "MB" in format_size(5 * 1024 * 1024)

def test_format_size_gb():
    assert "GB" in format_size(2 * 1024 ** 3)

def test_build_summary_text():
    from cleaner import CleanResult
    r = CleanResult(moved=5, errors=1, bytes_freed=1024 * 1024 * 50)
    text = build_summary_text(r)
    assert "5" in text
    assert "50" in text  # 50 MB
    assert "error" in text.lower()
