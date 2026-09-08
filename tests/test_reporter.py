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

def test_build_summary_text_points_at_the_error_log_when_errors_occur():
    from cleaner import CleanResult
    text = build_summary_text(CleanResult(moved=1, errors=3))
    assert "mac-maid-error.log" in text

def test_build_summary_text_reports_skipped_duplicates():
    from cleaner import CleanResult
    text = build_summary_text(CleanResult(moved=2, skipped=7))
    assert "7" in text
    assert "skip" in text.lower()

def test_build_summary_text_silent_when_nothing_skipped_or_failed():
    from cleaner import CleanResult
    text = build_summary_text(CleanResult(moved=2, bytes_freed=10))
    assert "skip" not in text.lower()
    assert "error" not in text.lower()


def test_summary_separates_a_changed_path_from_a_duplicate():
    """Two different reasons for not deleting something. Reporting both as
    'duplicate or already-covered' hides the one that matters."""
    from cleaner import CleanResult
    from reporter import build_summary_text

    text = build_summary_text(CleanResult(
        moved=1, bytes_freed=10, skipped=2,
        changed_paths=["/tmp/proj/node_modules"],
    ))

    assert "Left alone: 1 path(s) changed between the scan and the clean" in text
    assert "Skipped: 1 duplicate or already-covered path(s)" in text


def test_summary_says_nothing_about_skips_when_there_were_none():
    from cleaner import CleanResult
    from reporter import build_summary_text

    text = build_summary_text(CleanResult(moved=1, bytes_freed=10))

    assert "Left alone" not in text
    assert "Skipped" not in text
