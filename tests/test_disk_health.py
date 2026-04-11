from unittest.mock import patch
from modules.disk_health import scan

DISKUTIL_OUTPUT = """
   Device Identifier:         disk3s5
   Device Node:               /dev/disk3s5
   Total Size:                500.1 GB (500107862016 Bytes)
   Volume Free Space:         120.0 GB (120000000000 Bytes)
"""

def test_scan_parses_diskutil():
    with patch("modules.disk_health._run_diskutil", return_value=DISKUTIL_OUTPUT), \
         patch("modules.disk_health._run_smart", return_value="Verified"):
        result = scan()
    assert result["category"] == "Disk Health"
    assert result["risk"] == "inform-only"
    assert result["action"] == "none"
    assert len(result["items"]) > 0

def test_scan_smart_unavailable():
    with patch("modules.disk_health._run_diskutil", return_value=DISKUTIL_OUTPUT), \
         patch("modules.disk_health._run_smart", return_value=None):
        result = scan()
    assert result["category"] == "Disk Health"
