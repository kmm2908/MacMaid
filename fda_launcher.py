"""A tiny app for the hourly storage check, so Full Disk Access can be given to it alone.

macOS charges a process's file access to the program launchd started, and its children
inherit that. Granting the access to Python would hand it to every script that Python
runs; this app can only run the storage check, with its commands compiled in.
"""
import json
import subprocess
from pathlib import Path

from send2trash import send2trash

APP_DIR = Path.home() / ".local" / "share" / "MacMaid Storage Check.app"
EXECUTABLE = APP_DIR / "Contents" / "MacOS" / "storage-check"
SOURCE = APP_DIR / "Contents" / "Resources" / "storage-check.c"
BUNDLE_ID = "com.macmaid.storage-check"

INFO_PLIST = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>{BUNDLE_ID}</string>
    <key>CFBundleName</key>
    <string>MacMaid Storage Check</string>
    <key>CFBundleExecutable</key>
    <string>storage-check</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
"""

# Runs Python as a child, not by exec, so the access stays charged to this app. Nothing
# from the caller reaches it: a fixed environment, and Python's -E ignores PYTHON* settings.
# The only choice left to the caller is the read-only probe that proves the access works.
C_TEMPLATE = """#include <spawn.h>
#include <string.h>
#include <sys/wait.h>
int main(int argc, char *argv[]) {
    char *mode = (argc == 2 && strcmp(argv[1], "--storage-probe") == 0) ? "--storage-probe" : "--storage-check";
    char *args[] = {PYTHON, "-E", SCRIPT, mode, 0};
    char *env[] = {"HOME=" HOME, "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "LANG=en_GB.UTF-8", 0};
    pid_t pid;
    int status;
    if (posix_spawn(&pid, PYTHON, 0, 0, args, env) != 0) return 127;
    if (waitpid(pid, &status, 0) < 0) return 1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
"""


def _c_string(text: str) -> str:
    # JSON escapes quotes, backslashes and control characters as C does; other text stays UTF-8.
    return json.dumps(text, ensure_ascii=False)


def source(python: str, script: str) -> str:
    return "".join(f"#define {name} {_c_string(value)}\n" for name, value in
                   (("PYTHON", python), ("SCRIPT", script), ("HOME", str(Path.home())))) + C_TEMPLATE


def build(python: str, script: str) -> Path | None:
    """The app's executable, built only when its commands change. None if it could not be built.

    Rebuilding changes its signature, and macOS then forgets the access it was given.
    """
    wanted = source(python, script)
    if EXECUTABLE.exists() and SOURCE.exists() and SOURCE.read_text() == wanted:
        return EXECUTABLE
    try:
        EXECUTABLE.parent.mkdir(parents=True, exist_ok=True)
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        (APP_DIR / "Contents" / "Info.plist").write_text(INFO_PLIST)
        SOURCE.write_text(wanted)
        subprocess.run(["clang", "-O2", "-o", str(EXECUTABLE), str(SOURCE)],
                       check=True, capture_output=True)
        # Hardened runtime: no injected libraries in the process that holds the access.
        subprocess.run(["codesign", "--force", "--sign", "-", "--options", "runtime",
                        "--identifier", BUNDLE_ID, str(APP_DIR)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        # Nothing half-built is left to be granted access, and the next install tries again.
        SOURCE.unlink(missing_ok=True)
        EXECUTABLE.unlink(missing_ok=True)
        return None
    return EXECUTABLE


def remove() -> None:
    """Move the app to the Trash, so no access granted to it outlives the schedule."""
    if APP_DIR.exists():
        send2trash(str(APP_DIR))
