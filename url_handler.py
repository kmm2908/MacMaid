import stat
import subprocess
from pathlib import Path

BUNDLE_DIR = Path.home() / ".local" / "share" / "MacMaid.app"

_LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework"
    "/Versions/A/Frameworks/LaunchServices.framework"
    "/Versions/A/Support/lsregister"
)


def _info_plist() -> str:
    return """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.macmaid.app</string>
    <key>CFBundleName</key>
    <string>MacMaid</string>
    <key>CFBundleExecutable</key>
    <string>MacMaid</string>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key>
            <string>MacMaid Review</string>
            <key>CFBundleURLSchemes</key>
            <array>
                <string>macmaid</string>
            </array>
        </dict>
    </array>
</dict>
</plist>"""


def _executable(python_path: str, script_path: str) -> str:
    return f'#!/bin/bash\nexec "{python_path}" "{script_path}" --review\n'


def _create_bundle(python_path: str, script_path: str) -> None:
    contents = BUNDLE_DIR / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)

    plist_file = contents / "Info.plist"
    plist_file.write_text(_info_plist())

    exe = macos / "MacMaid"
    exe.write_text(_executable(python_path, script_path))
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
