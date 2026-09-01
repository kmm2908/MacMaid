import os
import subprocess
from unittest.mock import patch

from modules.dev_junk import scan


def _git(cwd, *args):
    """Fixture creation only — see tests/conftest.py."""
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
        cwd=cwd, check=True, capture_output=True, text=True, env=env,
    )


def _repo(root):
    _git(root, "init", "-q")
    with open(os.path.join(root, "README.md"), "w") as f:
        f.write("# repo\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "init")


def _patched(tmp_path):
    return [
        patch("modules.dev_junk.DEV_SCAN_PATHS", [str(tmp_path)]),
        patch("modules.dev_junk.XCODE_DERIVED", str(tmp_path / "xcode")),
        patch("modules.dev_junk.PIP_CACHE", str(tmp_path / "pip")),
        patch("modules.dev_junk.NPM_CACHE", str(tmp_path / "npm")),
    ]


def _scan(tmp_path):
    patches = _patched(tmp_path)
    for p in patches:
        p.start()
    try:
        return scan()
    finally:
        for p in patches:
            p.stop()


def test_finds_node_modules(tmp_path):
    _repo(str(tmp_path))
    proj = tmp_path / "myproject"
    (proj / "node_modules").mkdir(parents=True)
    (proj / "package.json").write_text("{}")
    _git(str(tmp_path), "add", "myproject/package.json")
    (proj / "node_modules" / "dep.js").write_text("x")

    labels = [i["label"] for i in _scan(tmp_path)["items"]]
    assert any("node_modules" in l for l in labels)


def test_finds_pycache(tmp_path):
    _repo(str(tmp_path))
    pc = tmp_path / "src" / "__pycache__"
    pc.mkdir(parents=True)
    (tmp_path / "src" / "mod.py").write_text("x = 1\n")
    _git(str(tmp_path), "add", "src/mod.py")
    (pc / "mod.cpython-311.pyc").write_bytes(b"bytecode")

    labels = [i["label"] for i in _scan(tmp_path)["items"]]
    assert any("__pycache__" in l for l in labels)


def test_result_is_safe(tmp_path):
    result = _scan(tmp_path)
    assert result["risk"] == "safe"
    assert result["category"] == "Dev Junk"
