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


def test_send_report_passes_action_and_urgent_to_the_sender():
    with patch("emailer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        send_report("S", "B", "t@example.com", action="do this")
        send_report("S", "B", "t@example.com", urgent="now")
    first, second = (c[0][0] for c in mock_run.call_args_list)
    assert first[first.index("--action") + 1] == "do this" and "--urgent" not in first
    assert second[second.index("--urgent") + 1] == "now" and "--action" not in second
