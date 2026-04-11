from unittest.mock import patch
from modules.login_items import scan

OSASCRIPT_OUTPUT = """Spotify, /Applications/Spotify.app, true
Dropbox, /Applications/Dropbox.app, true
DeadApp, /Applications/DeadApp.app, false
"""

def test_scan_parses_login_items():
    with patch("modules.login_items._run_osascript", return_value=OSASCRIPT_OUTPUT):
        result = scan()
    assert result["category"] == "Login Items"
    assert result["risk"] == "inform-only"
    assert result["action"] == "none"
    assert len(result["items"]) == 3

def test_scan_flags_dead_items():
    with patch("modules.login_items._run_osascript", return_value=OSASCRIPT_OUTPUT):
        result = scan()
    dead = [i for i in result["items"] if i["meta"].get("path_exists") is False]
    assert len(dead) >= 1

def test_scan_no_login_items():
    with patch("modules.login_items._run_osascript", return_value=""):
        result = scan()
    assert result["items"] == []
