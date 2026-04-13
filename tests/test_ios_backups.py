import os
import plistlib
from datetime import datetime, timezone
from unittest.mock import patch
from modules.ios_backups import scan


def _make_backup(base, name, device_name, last_backup: datetime | None = None):
    backup_dir = base / name
    backup_dir.mkdir()
    info = {"Display Name": device_name}
    if last_backup:
        info["Last Backup Date"] = last_backup
    with open(backup_dir / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    (backup_dir / "Manifest.db").write_bytes(b"x" * 1024)
    return backup_dir


def test_scan_finds_backups(tmp_path):
    _make_backup(tmp_path, "uuid-1", "Fred's iPhone",
                 datetime(2025, 6, 1, tzinfo=timezone.utc))
    _make_backup(tmp_path, "uuid-2", "Fred's iPad",
                 datetime(2024, 12, 1, tzinfo=timezone.utc))

    with patch("modules.ios_backups.BACKUP_DIR", str(tmp_path)):
        result = scan()

    assert result["category"] == "iOS Backups"
    assert result["risk"] == "review"
    assert len(result["items"]) == 2
    labels = [i["label"] for i in result["items"]]
    assert any("iPhone" in l for l in labels)
    assert any("iPad" in l for l in labels)


def test_scan_no_backup_dir(tmp_path):
    with patch("modules.ios_backups.BACKUP_DIR", str(tmp_path / "NoBackups")):
        result = scan()
    assert result["risk"] == "inform-only"
    assert result["items"] == []


def test_scan_sorted_newest_first(tmp_path):
    _make_backup(tmp_path, "old", "Old Phone", datetime(2023, 1, 1, tzinfo=timezone.utc))
    _make_backup(tmp_path, "new", "New Phone", datetime(2025, 1, 1, tzinfo=timezone.utc))

    with patch("modules.ios_backups.BACKUP_DIR", str(tmp_path)):
        result = scan()

    assert "New Phone" in result["items"][0]["label"]
