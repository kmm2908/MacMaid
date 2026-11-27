"""`--storage-check` through the real `main.main()`, as the hourly LaunchAgent invokes it.

It runs via `interactive_runner.py` with HOME moved. The free-space reading is real
and the thresholds are moved to force each level. The email sender and `osascript`
are stand-ins, so nothing is sent or shown. The notification script is compiled
(not run) by the real AppleScript compiler, and the last test checks that the
installed sender's help lists every option used.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import emailer
from tests.test_interactive_e2e import RUNNER, _user_base

ALWAYS = 1_000_000_000  # GB: no disk has this much free, so the reading is below it
NEVER = 0.000001


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = Path(os.path.realpath(tmp_path))
    home = root / "home"
    (home / "Library" / "Logs").mkdir(parents=True)
    for folder, size in (("Downloads", 900_000), (".Trash", 2_000)):
        (home / folder).mkdir()
        (home / folder / "blob").write_bytes(b"x" * size)
    sender = home / ".claude" / "utils" / "send_email.py"
    sender.parent.mkdir(parents=True)
    sender.write_text("import json, os, sys\n"
                      "open(os.environ['MM_ROOT'] + '/sent', 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
    osascript = root / "bin" / "osascript"
    osascript.parent.mkdir()
    osascript.write_text('#!/bin/sh\nprintf "%s\\n" "$2" >> "$MM_ROOT/notified"\n')
    osascript.chmod(0o755)
    return root


def run_check(root: Path, warn_gb: float, urgent_gb: float) -> None:
    (root / "config.json").write_text(json.dumps({
        "storage_warn_gb": warn_gb, "storage_urgent_gb": urgent_gb,
        "email_report_to": "t@example.com",
    }))
    env = dict(os.environ, HOME=str(root / "home"), MM_ROOT=str(root),
               PATH=f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}",
               PYTHONUSERBASE=os.environ.get("PYTHONUSERBASE") or _user_base())
    done = subprocess.run([sys.executable, "-B", RUNNER, "--storage-check"], env=env, check=False,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr


def sent(root: Path) -> list[list[str]]:
    log = root / "sent"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def option(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


def saved_level(root: Path) -> str:
    state = root / "home" / "Library" / "Logs" / "mac-maid-storage-state.json"
    return str(json.loads(state.read_text())["level"])


@pytest.mark.parametrize("urgent_gb, level, flag, other", [
    (NEVER, "warn", "--action", "--urgent"),
    (ALWAYS, "urgent", "--urgent", "--action"),
])
def test_low_disk_emails_and_notifies_once(root: Path, urgent_gb: float, level: str,
                                           flag: str, other: str) -> None:
    run_check(root, ALWAYS, urgent_gb)
    run_check(root, ALWAYS, urgent_gb)  # the next hour stays quiet

    [command] = sent(root)
    assert option(command, "--to") == "t@example.com"
    assert flag in command and other not in command
    assert "free on the main disk" in option(command, "--subject")
    body = option(command, "--body")
    assert 0 <= body.find("  Trash: ") < body.find("  Downloads: ")  # smaller, still first
    [script] = (root / "notified").read_text().splitlines()
    assert script.startswith("display notification ") and "disk nearly full" in script
    compiled = subprocess.run(["osacompile", "-o", str(root / "banner.scpt"), "-e", script],
                              check=False, capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stderr
    assert saved_level(root) == level


def test_enough_space_sends_nothing(root: Path) -> None:
    run_check(root, NEVER, NEVER)

    assert sent(root) == [] and not (root / "notified").exists()
    assert saved_level(root) == "ok"


def test_the_installed_sender_lists_every_option_used(root: Path) -> None:
    """The stand-in above accepts anything; the real sender must know every option."""
    run_check(root, ALWAYS, NEVER)
    run_check(root, ALWAYS, ALWAYS)
    used = {arg for command in sent(root) for arg in command[::2]}
    assert {"--to", "--subject", "--body", "--action", "--urgent"} <= used

    real = subprocess.run([sys.executable, emailer.EMAIL_SCRIPT, "--help"], check=False,
                          capture_output=True, text=True, timeout=30)
    assert real.returncode == 0, real.stderr
    known = {word.strip(",[]") for word in real.stdout.split()}
    assert used <= known, used - known
