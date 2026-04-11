import os
from unittest.mock import patch
from scheduler import build_plist, PLIST_PATH

def test_build_plist_contains_hour():
    plist = build_plist("02:30")
    assert "<integer>2</integer>" in plist
    assert "<integer>30</integer>" in plist

def test_build_plist_contains_script_path():
    plist = build_plist("02:00")
    assert "main.py" in plist

def test_plist_path_is_in_launch_agents():
    assert "LaunchAgents" in PLIST_PATH
    assert "com.macmaid" in PLIST_PATH
