import subprocess
import sys
from pathlib import Path

EMAIL_SCRIPT = str(Path.home() / ".claude" / "utils" / "send_email.py")


def send_report(subject: str, body: str, to: str, html_body: str | None = None) -> bool:
    try:
        cmd = [sys.executable, EMAIL_SCRIPT, "--to", to, "--subject", subject, "--body", body]
        if html_body:
            cmd += ["--html-body", html_body]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False
