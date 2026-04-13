import json
from unittest.mock import patch
from modules.thermal import scan

POWERMETRICS_JSON = json.dumps({
    "thermal_pressure": "Nominal",
    "processor": {
        "clusters": [
            {"name": "E-Cluster", "die_temperature": 42.5},
            {"name": "P-Cluster", "die_temperature": 58.0},
        ],
        "cpu_power": 3.2,
    },
    "gpu": {
        "die_temperature": 45.0,
    }
})

def test_scan_parses_powermetrics():
    with patch("modules.thermal._has_passwordless_sudo", return_value=True), \
         patch("modules.thermal._run_powermetrics", return_value=POWERMETRICS_JSON):
        result = scan()
    assert result["category"] == "Thermal & Performance"
    assert result["risk"] == "inform-only"
    assert result["action"] == "none"
    labels = [i["label"] for i in result["items"]]
    assert any("Thermal Pressure" in l for l in labels)
    assert any("E-Cluster" in l for l in labels)

def test_scan_nominal_pressure():
    with patch("modules.thermal._has_passwordless_sudo", return_value=True), \
         patch("modules.thermal._run_powermetrics", return_value=POWERMETRICS_JSON):
        result = scan()
    pressure_item = next(i for i in result["items"] if "Thermal Pressure" in i["label"])
    assert "Nominal" in pressure_item["label"]

def test_scan_no_sudo():
    with patch("modules.thermal._has_passwordless_sudo", return_value=False), \
         patch("modules.thermal.getpass.getuser", return_value="testuser"):
        result = scan()
    assert result["category"] == "Thermal & Performance"
    assert result["risk"] == "inform-only"
    assert any("skipped" in i["label"].lower() for i in result["items"])
    assert "testuser" in result["suggestion"]
    assert "visudo" in result["suggestion"]

def test_scan_powermetrics_unavailable():
    with patch("modules.thermal._has_passwordless_sudo", return_value=True), \
         patch("modules.thermal._run_powermetrics", return_value=None):
        result = scan()
    assert result["category"] == "Thermal & Performance"
    assert any("unavailable" in i["label"].lower() for i in result["items"])

def test_scan_high_pressure_adds_suggestion():
    hot_data = json.loads(POWERMETRICS_JSON)
    hot_data["thermal_pressure"] = "Heavy"
    with patch("modules.thermal._has_passwordless_sudo", return_value=True), \
         patch("modules.thermal._run_powermetrics", return_value=json.dumps(hot_data)):
        result = scan()
    assert "throttl" in result["suggestion"].lower() or "heavy" in result["suggestion"].lower()
