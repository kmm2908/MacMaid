"""The storage-check app: it may run the storage check and the probe, nothing else."""
import subprocess
from unittest.mock import patch

import pytest

import fda_launcher
import scheduler
import storage_watch as sw


@pytest.fixture
def app(tmp_path):
    """The app built into a temp folder, with a stand-in Python that records what it is asked to run."""
    root = tmp_path / "Odd \"name\" \\ dir"
    root.mkdir()
    python = root / "python3"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$(dirname "$0")/ran"\nenv > "$(dirname "$0")/env"\nexit 7\n')
    python.chmod(0o755)
    app_dir = tmp_path / "MacMaid Storage Check.app"
    with patch.object(fda_launcher, "APP_DIR", app_dir), \
         patch.object(fda_launcher, "EXECUTABLE", app_dir / "Contents" / "MacOS" / "storage-check"), \
         patch.object(fda_launcher, "SOURCE", app_dir / "Contents" / "Resources" / "storage-check.c"):
        built = fda_launcher.build(str(python), str(root / "main.py"))
        yield built, root


def run(app, *args, env=None):
    built, root = app
    code = subprocess.run([str(built), *args], check=False, env=env).returncode
    return code, (root / "ran").read_text().splitlines()


def test_it_runs_the_storage_check_and_passes_back_its_exit_code(app):
    code, ran = run(app)
    assert code == 7
    assert ran == ["-E", str(app[1] / "main.py"), "--storage-check"]


def test_the_probe_is_the_only_other_thing_it_will_run(app):
    assert run(app, "--storage-probe")[1][2:] == ["--storage-probe"]
    for args in (["--unattended"], ["--storage-probe", "--unattended"], ["; rm -rf ~"]):
        assert run(app, *args)[1][2:] == ["--storage-check"]


def test_nothing_in_the_callers_environment_reaches_python(app):
    run(app, env={"PYTHONSTARTUP": "/evil.py", "PYTHONPATH": "/evil", "DYLD_INSERT_LIBRARIES": "/evil.dylib",
                  "PATH": "/evil/bin", "HOME": "/evil"})
    env = dict(line.split("=", 1) for line in (app[1] / "env").read_text().splitlines() if "=" in line)
    assert not [k for k in env if k.startswith(("PYTHON", "DYLD"))]
    assert env["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert env["HOME"] == str(fda_launcher.Path.home())


def test_it_is_signed_under_its_own_identifier(app):
    shown = subprocess.run(["codesign", "-dv", str(fda_launcher.APP_DIR)], capture_output=True, text=True)
    assert "Identifier=com.macmaid.storage-check" in shown.stderr
    assert "(adhoc,runtime)" in shown.stderr


def test_an_unchanged_app_is_not_rebuilt_so_its_access_is_kept(app):
    built, root = app
    before = built.stat().st_mtime_ns
    assert fda_launcher.build(str(root / "python3"), str(root / "main.py")) == built
    assert built.stat().st_mtime_ns == before
    fda_launcher.build(str(root / "python3"), str(root / "elsewhere.py"))
    assert built.stat().st_mtime_ns != before


def test_a_failed_build_reports_none_and_tries_again_next_time(tmp_path):
    app_dir = tmp_path / "x.app"
    source = app_dir / "Contents" / "Resources" / "storage-check.c"
    with patch.object(fda_launcher, "APP_DIR", app_dir), \
         patch.object(fda_launcher, "EXECUTABLE", app_dir / "Contents" / "MacOS" / "storage-check"), \
         patch.object(fda_launcher, "SOURCE", source), \
         patch("fda_launcher.subprocess.run", side_effect=subprocess.CalledProcessError(1, "codesign")):
        (app_dir / "Contents" / "MacOS").mkdir(parents=True)
        (app_dir / "Contents" / "MacOS" / "storage-check").write_text("unsigned")
        assert fda_launcher.build("/usr/bin/python3", "/x/main.py") is None
    assert not source.exists()
    assert not (app_dir / "Contents" / "MacOS" / "storage-check").exists()


def test_unscheduling_moves_the_app_to_the_trash(tmp_path):
    app_dir = tmp_path / "x.app"
    app_dir.mkdir()
    with patch.object(fda_launcher, "APP_DIR", app_dir), patch("fda_launcher.send2trash") as trash, \
         patch.object(scheduler, "PLIST_PATH", str(tmp_path / "none")), \
         patch.object(scheduler, "STORAGE_PLIST_PATH", str(tmp_path / "none2")):
        scheduler.uninstall()
    trash.assert_called_once_with(str(app_dir))


def test_a_path_with_xml_or_unicode_survives(tmp_path):
    plist = scheduler.build_storage_plist(["/a & b/<c>/café"])
    assert "<string>/a &amp; b/&lt;c&gt;/café</string>" in plist
    assert '"/x/café \\"q\\".py"' in fda_launcher.source("/py", '/x/café "q".py')


def test_the_hourly_agent_runs_the_app_alone():
    plist = scheduler.build_storage_plist(["/apps/MacMaid Storage Check.app/Contents/MacOS/storage-check"])
    args = plist.split("<array>")[1].split("</array>")[0]
    assert args.split() == ["<string>/apps/MacMaid", "Storage",
                            "Check.app/Contents/MacOS/storage-check</string>"]


def test_a_blocked_alert_names_the_app_once_it_exists(tmp_path):
    exe = tmp_path / "storage-check"
    exe.write_text("")
    with patch.object(sw.fda_launcher, "EXECUTABLE", exe):
        text = "\n".join(sw._access_lines())
    assert "MacMaid Storage Check" in text and sw.sys.executable not in text


def test_the_probe_flag_prints_each_measurement(capsys):
    import main
    users = [("Trash", sw.Measure(None, complete=False, blocked=True)), ("Mail", sw.Measure(2_000_000_000))]
    with patch("sys.argv", ["main.py", "--storage-probe"]), patch.object(sw, "top_users", return_value=users):
        main.main()
    assert capsys.readouterr().out.splitlines() == [
        "Trash: could not be measured (macOS blocked access)", "Mail: 2.0 GB"]
