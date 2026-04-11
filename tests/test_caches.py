import os
from unittest.mock import patch
from modules.caches import scan

def test_scan_finds_cache_dirs(tmp_path):
    user_cache = tmp_path / "UserCache"
    app_dir = user_cache / "com.example.app"
    app_dir.mkdir(parents=True)
    (app_dir / "cache.db").write_bytes(b"x" * 1024)

    with patch("modules.caches.USER_CACHE_DIR", str(user_cache)), \
         patch("modules.caches.SYS_CACHE_DIR", str(tmp_path / "SysCache")):
        result = scan()

    assert result["category"] == "Caches"
    assert result["risk"] == "safe"
    assert result["action"] == "trash"
    assert len(result["items"]) >= 1
    assert result["total_size_bytes"] >= 1024

def test_scan_empty_cache(tmp_path):
    with patch("modules.caches.USER_CACHE_DIR", str(tmp_path / "empty")), \
         patch("modules.caches.SYS_CACHE_DIR", str(tmp_path / "empty2")):
        result = scan()
    assert result["total_size_bytes"] == 0
    assert result["items"] == []

def test_scan_groups_by_app(tmp_path):
    user_cache = tmp_path / "UserCache"
    (user_cache / "com.example.app").mkdir(parents=True)
    (user_cache / "com.example.app" / "a.bin").write_bytes(b"x" * 512)
    (user_cache / "com.example.app" / "b.bin").write_bytes(b"x" * 512)

    with patch("modules.caches.USER_CACHE_DIR", str(user_cache)), \
         patch("modules.caches.SYS_CACHE_DIR", str(tmp_path / "sys")):
        result = scan()

    # com.example.app should appear as one item (the directory)
    labels = [i["label"] for i in result["items"]]
    assert "com.example.app" in labels
