import os
import subprocess
import time

from modules import dev_junk

# Fixture repositories are back-dated past the dormancy window, so these tests
# keep testing the installed-software discriminator rather than liveness. The
# offset is derived from the production constant, not restated, so the fixtures
# cannot drift away from the rule they are meant to sit outside of.
_FIXTURE_COMMIT_AGE = (dev_junk.DORMANT_DAYS_DEFAULT + 30) * 86400


def _git(cwd, *args):
    """Fixture creation only — see tests/conftest.py."""
    stamp = f"{int(time.time() - _FIXTURE_COMMIT_AGE)} +0000"
    env = dict(
        os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
        GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp,
    )
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


def _age_out(*paths: str) -> None:
    """Dormancy now also asks whether the files were touched recently, so a
    fixture built one millisecond ago reads as live work. Back-date it to the
    same point as the commits, and these tests keep testing what they are for."""
    stamp = time.time() - _FIXTURE_COMMIT_AGE
    for p in paths:
        os.utime(p, (stamp, stamp))


def _make(root, rel, track=()):
    p = os.path.join(root, rel)
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, "f.txt"), "w") as f:
        f.write("x" * 10)
    for name in track:
        tracked = os.path.join(os.path.dirname(p), name)
        with open(tracked, "w") as f:
            f.write("{}")
        _git(root, "add", tracked)
        _git(root, "commit", "-qm", f"add {name}")
        _age_out(tracked)
    _age_out(os.path.join(p, "f.txt"), p, os.path.dirname(p))
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
