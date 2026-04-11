from unittest.mock import patch, MagicMock
from emailer import send_report

def test_send_report_calls_script():
    with patch("emailer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = send_report("Test Subject", "Test body", "test@example.com")
    assert result is True
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "send_email.py" in " ".join(args)

def test_send_report_returns_false_on_failure():
    with patch("emailer.subprocess.run", side_effect=Exception("SMTP error")):
        result = send_report("Subject", "Body", "test@example.com")
    assert result is False
