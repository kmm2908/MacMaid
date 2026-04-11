import os
from unittest.mock import patch
from modules.dev_junk import scan

def test_finds_node_modules(tmp_path):
    nm = tmp_path / "myproject" / "node_modules"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text("{}")

    with patch("modules.dev_junk.DEV_SCAN_PATHS", [str(tmp_path)]), \
         patch("modules.dev_junk.XCODE_DERIVED", str(tmp_path / "xcode")), \
         patch("modules.dev_junk.PIP_CACHE", str(tmp_path / "pip")), \
         patch("modules.dev_junk.NPM_CACHE", str(tmp_path / "npm")):
        result = scan()

    labels = [i["label"] for i in result["items"]]
    assert any("node_modules" in l for l in labels)

def test_finds_pycache(tmp_path):
    pc = tmp_path / "src" / "__pycache__"
    pc.mkdir(parents=True)
    (pc / "mod.cpython-311.pyc").write_bytes(b"bytecode")

    with patch("modules.dev_junk.DEV_SCAN_PATHS", [str(tmp_path)]), \
         patch("modules.dev_junk.XCODE_DERIVED", str(tmp_path / "xcode")), \
         patch("modules.dev_junk.PIP_CACHE", str(tmp_path / "pip")), \
         patch("modules.dev_junk.NPM_CACHE", str(tmp_path / "npm")):
        result = scan()

    labels = [i["label"] for i in result["items"]]
    assert any("__pycache__" in l for l in labels)

def test_result_is_safe(tmp_path):
    with patch("modules.dev_junk.DEV_SCAN_PATHS", [str(tmp_path)]), \
         patch("modules.dev_junk.XCODE_DERIVED", str(tmp_path / "xcode")), \
         patch("modules.dev_junk.PIP_CACHE", str(tmp_path / "pip")), \
         patch("modules.dev_junk.NPM_CACHE", str(tmp_path / "npm")):
        result = scan()
    assert result["risk"] == "safe"
    assert result["category"] == "Dev Junk"
