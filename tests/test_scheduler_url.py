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


def test_install_writes_and_loads_both_agents(tmp_path):
    nightly, storage = tmp_path / "n.plist", tmp_path / "s.plist"
    with patch.object(scheduler, "PLIST_PATH", str(nightly)), \
         patch.object(scheduler, "STORAGE_PLIST_PATH", str(storage)), \
         patch("scheduler.url_handler"), \
         patch("scheduler.subprocess.run") as run:
        assert scheduler.install("02:00")
    assert "--storage-check" in storage.read_text()
    loaded = [c[0][0][2] for c in run.call_args_list if c[0][0][1] == "load"]
    assert loaded == [str(nightly), str(storage)]


def test_uninstall_reports_failure_instead_of_crashing(tmp_path):
    nightly = tmp_path / "n.plist"
    nightly.write_text("x")
    with patch.object(scheduler, "PLIST_PATH", str(nightly)), \
         patch.object(scheduler, "STORAGE_PLIST_PATH", str(tmp_path / "none.plist")), \
         patch("scheduler.subprocess.run"), \
         patch("scheduler.os.remove", side_effect=PermissionError("nope")):
        assert scheduler.uninstall() is False


def test_status_says_storage_check_is_off_when_launchd_has_not_loaded_it(tmp_path):
    nightly, storage = tmp_path / "n.plist", tmp_path / "s.plist"
    nightly.write_text("x")
    storage.write_text("x")
    with patch.object(scheduler, "PLIST_PATH", str(nightly)), \
         patch.object(scheduler, "STORAGE_PLIST_PATH", str(storage)), \
         patch("scheduler.subprocess.run", return_value=MagicMock(returncode=113)):
        assert "storage check not loaded" in scheduler.status()
