import os
import time

from modules.base import is_removable
from modules import logs


def test_normal_file_in_writable_dir_is_removable(tmp_path):
    f = tmp_path / "a.log"
    f.write_text("x")
    assert is_removable(str(f))


def test_file_in_readonly_parent_is_not_removable(tmp_path):
    d = tmp_path / "locked"
    d.mkdir()
    f = d / "a.log"
    f.write_text("x")
    os.chmod(d, 0o555)
    try:
        assert not is_removable(str(f))
    finally:
        os.chmod(d, 0o755)


def test_root_owned_path_is_not_removable():
    # /private/var/log is root-owned; the nightly run can never delete from it.
    if os.path.isdir("/private/var/log") and os.geteuid() != 0:
        assert not is_removable("/private/var/log/wifi.log")


def test_missing_path_is_not_removable(tmp_path):
    assert not is_removable(str(tmp_path / "gone.log"))


def test_logs_scan_excludes_unremovable_system_logs(monkeypatch, tmp_path):
    """The real bug: 24/24 log items lived in /private/var/log and failed every run."""
    user_dir = tmp_path / "userlogs"
    user_dir.mkdir()
    old = user_dir / "old.log"
    old.write_text("x" * 100)
    ancient = time.time() - (400 * 86400)
    os.utime(old, (ancient, ancient))

    monkeypatch.setattr(logs, "USER_LOG_DIR", str(user_dir))
    monkeypatch.setattr(logs, "SYS_LOG_DIR", "/private/var/log")

    result = logs.scan()
    paths = [i["path"] for i in result["items"]]
    assert str(old) in paths
    assert not any(p.startswith("/private/var/log") for p in paths), paths
