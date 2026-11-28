"""Run the real main.main() for the terminal tests, inside a throwaway fixture.

Every location outside HOME is redirected into MM_ROOT, send2trash is replaced
(the real one would fill the developer's Trash), and cleaning anything outside
MM_ROOT is refused.
"""
import os
import shutil
import sys

ROOT = os.path.realpath(os.environ["MM_ROOT"])
assert os.path.realpath(os.path.expanduser("~")) == os.path.join(ROOT, "home")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# before main is imported: some modules read the config at import time
config.CONFIG_PATH = os.path.join(ROOT, "config.json")

import cleaner
import main
from modules import base, caches, login_items, logs, thermal, trash

caches.SYS_CACHE_DIR = os.path.join(ROOT, "syscaches")
logs.SYS_LOG_DIR = os.path.join(ROOT, "syslogs")
trash.VOLUMES_DIR = os.path.join(ROOT, "volumes")
base.added_time = lambda path: os.lstat(path).st_mtime
login_items._run_osascript = lambda: ""
thermal._has_passwordless_sudo = lambda: False
main.cleaner_mod.ERROR_LOG_PATH = main.Path(ROOT) / "error.log"


def _fake_send2trash(path: str) -> None:
    if os.path.basename(path).startswith("locked"):
        raise OSError("Operation not permitted")
    binned = os.path.join(ROOT, "binned")
    os.makedirs(binned, exist_ok=True)
    shutil.move(path, os.path.join(binned, os.path.basename(path)))


_real_clean_items = cleaner.clean_items


def _clean_inside_fixture_only(items, **kwargs):
    for item in items:
        assert os.path.realpath(item["path"]).startswith(ROOT + os.sep), item["path"]
    return _real_clean_items(items, **kwargs)


cleaner.send2trash = _fake_send2trash
cleaner.clean_items = _clean_inside_fixture_only
sys.argv = ["main.py", "--terminal", *sys.argv[1:]]
main.main()
