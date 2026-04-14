from unittest.mock import patch, MagicMock
import scheduler


def test_install_calls_url_handler_setup():
    setup_calls = []
    with patch("scheduler.url_handler") as mock_uh, \
         patch("builtins.open", MagicMock()), \
         patch("subprocess.run", MagicMock()):
        mock_uh.setup = lambda *a: setup_calls.append(a)
        scheduler.install("02:00")

    assert len(setup_calls) == 1
    python_arg, script_arg = setup_calls[0]
    assert "python" in python_arg.lower()
    assert "main.py" in script_arg
