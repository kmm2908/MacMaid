import os

from modules import dev_junk


def _make(root, rel):
    p = os.path.join(root, rel)
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, "f.txt"), "w") as f:
        f.write("x" * 10)
    return p


def test_scan_path_skips_home_trash(tmp_path):
    root = str(tmp_path)
    _make(root, "project/node_modules")
    _make(root, ".Trash/old-project/node_modules")
    items = []
    dev_junk._scan_path(root, items)
    paths = [i["path"] for i in items]
    assert any("project/node_modules" in p and ".Trash" not in p for p in paths)
    assert not any(".Trash" in p for p in paths), paths


def test_scan_path_skips_volume_trashes(tmp_path):
    root = str(tmp_path)
    _make(root, ".Trashes/501/old/__pycache__")
    _make(root, "live/__pycache__")
    items = []
    dev_junk._scan_path(root, items)
    paths = [i["path"] for i in items]
    assert not any(".Trashes" in p for p in paths), paths
    assert len(paths) == 1


def test_scan_path_skips_pyc_files_inside_trash(tmp_path):
    root = str(tmp_path)
    trash = os.path.join(root, ".Trash")
    os.makedirs(trash, exist_ok=True)
    with open(os.path.join(trash, "stale.pyc"), "w") as f:
        f.write("x")
    with open(os.path.join(root, "live.pyc"), "w") as f:
        f.write("x")
    items = []
    dev_junk._scan_path(root, items)
    paths = [i["path"] for i in items]
    assert paths == [os.path.join(root, "live.pyc")], paths
