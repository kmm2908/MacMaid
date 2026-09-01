import os
import subprocess

from modules import dev_junk


def _git(cwd, *args):
    """Fixture creation only — see tests/conftest.py."""
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
        cwd=cwd, check=True, capture_output=True, text=True, env=env,
    )


def _repo(root):
    """dev_junk only offers artefacts whose own directory holds tracked source."""
    _git(root, "init", "-q")
    with open(os.path.join(root, "README.md"), "w") as f:
        f.write("# repo\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "init")


def _make(root, rel, track=()):
    p = os.path.join(root, rel)
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, "f.txt"), "w") as f:
        f.write("x" * 10)
    for name in track:
        with open(os.path.join(os.path.dirname(p), name), "w") as f:
            f.write("{}")
        _git(root, "add", os.path.join(os.path.dirname(p), name))
    return p


def test_scan_path_skips_home_trash(tmp_path):
    root = str(tmp_path)
    _repo(root)
    _make(root, "project/node_modules", track=("package.json",))
    _make(root, ".Trash/old-project/node_modules", track=("package.json",))
    items = []
    dev_junk._scan_path(root, items)
    paths = [i["path"] for i in items]
    assert any("project/node_modules" in p and ".Trash" not in p for p in paths)
    assert not any(".Trash" in p for p in paths), paths


def test_scan_path_skips_volume_trashes(tmp_path):
    root = str(tmp_path)
    _repo(root)
    _make(root, ".Trashes/501/old/__pycache__")
    live = _make(root, "live/__pycache__", track=("mod.py",))
    with open(os.path.join(live, "mod.cpython-312.pyc"), "w") as f:
        f.write("x")
    items = []
    dev_junk._scan_path(root, items)
    paths = [i["path"] for i in items]
    assert not any(".Trashes" in p for p in paths), paths
    assert len(paths) == 1


def test_scan_path_skips_pyc_files_inside_trash(tmp_path):
    root = str(tmp_path)
    _repo(root)
    with open(os.path.join(root, "mod.py"), "w") as f:
        f.write("x = 1\n")
    _git(root, "add", "mod.py")
    trash = os.path.join(root, ".Trash")
    os.makedirs(trash, exist_ok=True)
    with open(os.path.join(trash, "stale.pyc"), "w") as f:
        f.write("x")
    with open(os.path.join(root, "mod.pyc"), "w") as f:
        f.write("x")
    items = []
    dev_junk._scan_path(root, items)
    paths = [i["path"] for i in items]
    assert paths == [os.path.join(root, "mod.pyc")], paths
