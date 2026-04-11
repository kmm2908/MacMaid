import subprocess
import json
from modules.base import make_result, make_item

PRESSURE_LEVELS = ["Nominal", "Light", "Moderate", "Heavy", "Critical"]


def _run_powermetrics() -> str | None:
    try:
        out = subprocess.check_output(
            ["sudo", "/usr/bin/powermetrics",
             "--samplers", "smc,cpu_power",
             "-n", "1",
             "--output-format", "json"],
            text=True, timeout=30, stderr=subprocess.DEVNULL
        )
        return out.strip().lstrip("\x00")
    except subprocess.CalledProcessError:
        return None
    except Exception:
        return None


def scan() -> dict:
    raw = _run_powermetrics()

    if not raw:
        return make_result(
            "Thermal & Performance",
            "inform-only",
            action="none",
            suggestion="Requires sudo access. Add sudoers rule: fred ALL=(ALL) NOPASSWD: /usr/bin/powermetrics",
            items=[make_item("powermetrics", 0, "Thermal data unavailable — sudoers rule needed")],
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return make_result(
            "Thermal & Performance", "inform-only", action="none",
            suggestion="Could not parse powermetrics output",
            items=[make_item("powermetrics", 0, "Parse error")],
        )

    items = []
    pressure = data.get("thermal_pressure", "Unknown")
    items.append(make_item("thermal", 0, f"Thermal Pressure: {pressure}"))

    processor = data.get("processor", {})
    for cluster in processor.get("clusters", []):
        name = cluster.get("name", "Cluster")
        temp = cluster.get("die_temperature", 0)
        items.append(make_item("thermal", 0, f"{name}: {temp:.1f}°C"))

    gpu = data.get("gpu", {})
    if "die_temperature" in gpu:
        items.append(make_item("thermal", 0, f"GPU: {gpu['die_temperature']:.1f}°C"))

    cpu_power = processor.get("cpu_power", 0)
    items.append(make_item("thermal", 0, f"CPU Power: {cpu_power:.1f}W"))

    pressure_idx = PRESSURE_LEVELS.index(pressure) if pressure in PRESSURE_LEVELS else 0
    throttling = pressure_idx >= 2  # Moderate or above
    items.append(make_item("thermal", 0, f"Throttling: {'YES — performance reduced' if throttling else 'No'}"))

    if throttling:
        suggestion = f"Thermal pressure is {pressure} — CPU is throttling. Close unused apps and check Activity Monitor."
    else:
        suggestion = f"Thermal pressure is {pressure} — system running normally"

    return make_result(
        "Thermal & Performance",
        "inform-only",
        action="none",
        suggestion=suggestion,
        items=items,
    )
