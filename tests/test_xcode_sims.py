import os
import plistlib
from unittest.mock import patch
from modules.xcode_sims import scan


def _make_sim(base, name, device_name, state, runtime="com.apple.CoreSimulator.SimRuntime.iOS-17-0"):
    sim_dir = base / name
    sim_dir.mkdir()
    info = {"name": device_name, "state": state, "runtime": runtime}
    with open(sim_dir / "device.plist", "wb") as f:
        plistlib.dump(info, f)
    (sim_dir / "data").mkdir()
    (sim_dir / "data" / "file.bin").write_bytes(b"x" * 2048)
    return sim_dir


def test_scan_finds_shutdown_simulators(tmp_path):
    _make_sim(tmp_path, "sim-1", "iPhone 15", "Shutdown")
    _make_sim(tmp_path, "sim-2", "iPad Pro", "Shutdown")

    with patch("modules.xcode_sims.SIM_DIR", str(tmp_path)):
        result = scan()

    assert result["category"] == "Xcode Simulators"
    assert result["risk"] == "safe"
    assert len(result["items"]) == 2


def test_scan_skips_booted_simulators(tmp_path):
    _make_sim(tmp_path, "sim-running", "iPhone 15", "Booted")
    _make_sim(tmp_path, "sim-off", "iPhone 14", "Shutdown")

    with patch("modules.xcode_sims.SIM_DIR", str(tmp_path)):
        result = scan()

    assert len(result["items"]) == 1
    assert "iPhone 14" in result["items"][0]["label"]


def test_scan_no_sim_dir(tmp_path):
    with patch("modules.xcode_sims.SIM_DIR", str(tmp_path / "NoSims")):
        result = scan()
    assert result["risk"] == "inform-only"
    assert result["items"] == []


def test_scan_no_shutdown_sims(tmp_path):
    _make_sim(tmp_path, "sim-1", "iPhone 15", "Booted")

    with patch("modules.xcode_sims.SIM_DIR", str(tmp_path)):
        result = scan()

    assert result["risk"] == "inform-only"
    assert result["items"] == []


def test_runtime_label_shortened(tmp_path):
    _make_sim(tmp_path, "sim-1", "iPhone 15", "Shutdown",
              runtime="com.apple.CoreSimulator.SimRuntime.iOS-17-0")

    with patch("modules.xcode_sims.SIM_DIR", str(tmp_path)):
        result = scan()

    assert "iOS 17.0" in result["items"][0]["label"]
