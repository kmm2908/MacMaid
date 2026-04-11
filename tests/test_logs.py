import os
import time
from unittest.mock import patch
from modules.logs import scan

def test_scan_finds_old_logs(tmp_path):
    log_dir = tmp_path / "Logs"
    log_dir.mkdir()
    old_log = log_dir / "old.log"
    old_log.write_text("old log data")
    # set mtime to 10 days ago
    old_time = time.time() - (10 * 86400)
    os.utime(str(old_log), (old_time, old_time))

    with patch("modules.logs.USER_LOG_DIR", str(log_dir)), \
         patch("modules.logs.SYS_LOG_DIR", str(tmp_path / "syslog")), \
         patch("modules.logs.RETENTION_DAYS", 7):
        result = scan()

    assert result["category"] == "Logs"
    assert result["risk"] == "safe"
    assert any("old.log" in i["label"] for i in result["items"])

def test_scan_ignores_recent_logs(tmp_path):
    log_dir = tmp_path / "Logs"
    log_dir.mkdir()
    recent = log_dir / "recent.log"
    recent.write_text("recent")
    # mtime = now (recent)

    with patch("modules.logs.USER_LOG_DIR", str(log_dir)), \
         patch("modules.logs.SYS_LOG_DIR", str(tmp_path / "syslog")), \
         patch("modules.logs.RETENTION_DAYS", 7):
        result = scan()

    assert not any("recent.log" in i["label"] for i in result["items"])

def test_scan_missing_dirs(tmp_path):
    with patch("modules.logs.USER_LOG_DIR", str(tmp_path / "nope")), \
         patch("modules.logs.SYS_LOG_DIR", str(tmp_path / "nope2")), \
         patch("modules.logs.RETENTION_DAYS", 7):
        result = scan()
    assert result["items"] == []
