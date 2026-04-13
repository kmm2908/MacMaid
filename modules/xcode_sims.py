import os
import plistlib
from modules.base import make_result, make_item

SIM_DIR = os.path.expanduser("~/Library/Developer/CoreSimulator/Devices")

# Simulators in these states can be safely removed
REMOVABLE_STATES = {"Shutdown"}


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _read_device_plist(sim_path: str) -> dict:
    plist_path = os.path.join(sim_path, "device.plist")
    try:
        with open(plist_path, "rb") as f:
            return plistlib.load(f)
    except Exception:
        return {}


def scan() -> dict:
    if not os.path.isdir(SIM_DIR):
        return make_result(
            "Xcode Simulators", "inform-only", action="none",
            suggestion="No Xcode simulators found (Xcode not installed or no simulators created)"
        )

    items = []
    try:
        entries = os.listdir(SIM_DIR)
    except OSError:
        entries = []

    for name in entries:
        full = os.path.join(SIM_DIR, name)
        if not os.path.isdir(full):
            continue
        info = _read_device_plist(full)
        state = info.get("state", "Unknown")
        # Skip running/booted simulators
        if state not in REMOVABLE_STATES and state != "Unknown":
            continue
        size = _dir_size(full)
        device_name = info.get("name") or name[:8]
        runtime = info.get("runtime", "")
        # Shorten runtime string: com.apple.CoreSimulator.SimRuntime.iOS-17-0 → iOS 17.0
        if "SimRuntime." in runtime:
            runtime = runtime.split("SimRuntime.")[-1].replace("-", " ", 1).replace("-", ".")
        label = f"{device_name} ({runtime})" if runtime else device_name
        items.append(make_item(full, size, label, meta={"state": state, "runtime": runtime}))

    items.sort(key=lambda x: x["size_bytes"], reverse=True)
    total = sum(i["size_bytes"] for i in items)
    size_gb = total / (1024 ** 3)

    if not items:
        return make_result(
            "Xcode Simulators", "inform-only", action="none",
            suggestion="No shutdown simulators found"
        )

    return make_result(
        "Xcode Simulators",
        "safe",
        action="trash",
        suggestion=f"{len(items)} shutdown simulator(s) found ({size_gb:.1f} GB) — safe to remove",
        items=items,
    )
