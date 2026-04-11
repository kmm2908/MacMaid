import subprocess
import sys
from pathlib import Path

EMAIL_SCRIPT = str(Path.home() / ".claude" / "utils" / "send_email.py")


def send_report(subject: str, body: str, to: str) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, EMAIL_SCRIPT, "--to", to, "--subject", subject, "--body", body],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False
