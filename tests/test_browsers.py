from unittest.mock import patch
from modules.browsers import scan

def test_scan_finds_browser_caches(tmp_path):
    safari = tmp_path / "Safari"
    safari.mkdir()
    (safari / "cache.db").write_bytes(b"x" * 2048)

    browser_dirs = {
        "Safari": str(safari),
        "Chrome": str(tmp_path / "Chrome"),
        "Firefox": str(tmp_path / "Firefox"),
    }
    with patch("modules.browsers.BROWSER_CACHE_DIRS", browser_dirs):
        result = scan()

    assert result["category"] == "Browser Caches"
    assert result["risk"] == "safe"
    assert any("Safari" in i["label"] for i in result["items"])
    assert result["total_size_bytes"] >= 2048

def test_scan_no_browser_caches(tmp_path):
    browser_dirs = {
        "Safari": str(tmp_path / "no_safari"),
        "Chrome": str(tmp_path / "no_chrome"),
        "Firefox": str(tmp_path / "no_firefox"),
    }
    with patch("modules.browsers.BROWSER_CACHE_DIRS", browser_dirs):
        result = scan()
    assert result["items"] == []
    assert result["total_size_bytes"] == 0
