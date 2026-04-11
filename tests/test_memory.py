from unittest.mock import patch
from modules.memory import scan

VM_STAT_OUTPUT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               12345.
Pages active:                             23456.
Pages inactive:                           11111.
Pages wired down:                         10000.
Pages compressor:                          5000.
"""

def test_scan_parses_vm_stat():
    with patch("modules.memory._run_vm_stat", return_value=VM_STAT_OUTPUT):
        result = scan()
    assert result["category"] == "Memory"
    assert result["risk"] == "inform-only"
    assert result["action"] == "none"
    assert len(result["items"]) > 0
    assert any("free" in i["label"].lower() for i in result["items"])

def test_scan_vm_stat_failure():
    with patch("modules.memory._run_vm_stat", return_value=""):
        result = scan()
    assert result["category"] == "Memory"
