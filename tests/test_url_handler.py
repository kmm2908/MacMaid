import stat
from pathlib import Path
import url_handler


def test_info_plist_registers_macmaid_scheme():
    plist = url_handler._info_plist()
    assert "<string>macmaid</string>" in plist
    assert "CFBundleURLSchemes" in plist
    assert "CFBundleIdentifier" in plist


def test_executable_contains_python_and_review_flag():
    exe = url_handler._executable("/usr/bin/python3", "/home/user/main.py")
    assert "/usr/bin/python3" in exe
    assert "/home/user/main.py" in exe
    assert "--review" in exe


def test_create_bundle_writes_expected_files(tmp_path, monkeypatch):
    monkeypatch.setattr(url_handler, "BUNDLE_DIR", tmp_path / "MacMaid.app")
    url_handler._create_bundle("/usr/bin/python3", "/home/user/main.py")

    plist_path = tmp_path / "MacMaid.app" / "Contents" / "Info.plist"
    exe_path = tmp_path / "MacMaid.app" / "Contents" / "MacOS" / "MacMaid"

    assert plist_path.exists()
    assert exe_path.exists()
    assert exe_path.stat().st_mode & stat.S_IXUSR  # executable bit set
    assert "<string>macmaid</string>" in plist_path.read_text()
    assert "/usr/bin/python3" in exe_path.read_text()
