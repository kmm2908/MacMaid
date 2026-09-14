import os
import pytest
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

@pytest.mark.parametrize("name", ["ms-playwright", "ms-playwright-mcp", "ms-playwright-go", "MS-PLAYWRIGHT-beta", "Cypress", "cypress"])
def test_scan_never_offers_installed_tool_binaries(tmp_path, name):
    user_cache = tmp_path / "UserCache"
    sys_cache = tmp_path / "SysCache"
    for base in (user_cache, sys_cache):
        (base / name / "chromium-1208").mkdir(parents=True)
        (base / name / "chromium-1208" / "chrome").write_bytes(b"x" * 4096)
        (base / "com.example.app").mkdir(parents=True)
        (base / "com.example.app" / "cache.db").write_bytes(b"x" * 1024)

    with patch("modules.caches.USER_CACHE_DIR", str(user_cache)), \
         patch("modules.caches.SYS_CACHE_DIR", str(sys_cache)):
        result = scan()

    labels = [i["label"] for i in result["items"]]
    assert name not in labels
    assert labels.count("com.example.app") == 2
    assert result["total_size_bytes"] == 2048

def test_scan_still_offers_tool_caches_that_refetch(tmp_path):
    user_cache = tmp_path / "UserCache"
    names = ["pip", "Homebrew", "pnpm", "node-gyp", "deno"]
    for name in names:
        (user_cache / name).mkdir(parents=True)
        (user_cache / name / "blob").write_bytes(b"x" * 256)

    with patch("modules.caches.USER_CACHE_DIR", str(user_cache)), \
         patch("modules.caches.SYS_CACHE_DIR", str(tmp_path / "SysCache")):
        result = scan()

    assert sorted(i["label"] for i in result["items"]) == sorted(names)
