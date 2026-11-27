import json
import sys
from unittest.mock import patch

import pytest

import config
import config_cli
import main

MODULES = ["caches", "downloads"]


@pytest.fixture
def cfg_file(tmp_path):
    path = tmp_path / "config.json"
    with patch("config.CONFIG_PATH", str(path)):
        config._reset()
        yield path
    config._reset()


def run(*argv):
    return config_cli.run(list(argv), MODULES)


def saved(path):
    return json.loads(path.read_text())


def test_show_lists_every_setting_and_marks_defaults(cfg_file, capsys):
    cfg_file.write_text(json.dumps({"old_file_days": 90, "modules": {"caches": False}}))
    assert run() == 0
    out = capsys.readouterr().out
    assert "old_file_days = 90\n" in out
    assert "log_retention_days = 7  (default)\n" in out
    assert "dev_junk_dormant_days = 180  (default)\n" in out
    assert "modules.caches = false\n" in out
    assert "modules.downloads = false  (default)\n" in out


def test_get_prints_one_effective_value(cfg_file, capsys):
    assert run("get", "scan_paths") == 0
    assert json.loads(capsys.readouterr().out) == config.DEFAULTS["scan_paths"]


@pytest.mark.parametrize("key,values,expected", [
    ("old_file_days", ["90"], 90),
    ("storage_warn_gb", ["12.5"], 12.5),
    ("permanent_delete", ["TRUE"], True),
    ("email_report_to", ["a@example.com"], "a@example.com"),
    ("email_report_to", [""], ""),
    ("scan_paths", ["~/Downloads", "/Volumes/Ext Data"], ["~/Downloads", "/Volumes/Ext Data"]),
])
def test_set_saves_typed_value(cfg_file, key, values, expected):
    assert run("set", key, *values) == 0
    assert saved(cfg_file) == {key: expected}
    assert config.get(key) == expected


def test_set_module_keeps_other_settings(cfg_file):
    cfg_file.write_text(json.dumps({"old_file_days": 90, "modules": {"caches": False}}))
    cfg_file.chmod(0o640)
    assert run("set", "modules.downloads", "true") == 0
    assert saved(cfg_file) == {"old_file_days": 90,
                               "modules": {"caches": False, "downloads": True}}
    assert cfg_file.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("argv", [
    ["set", "no_such_key", "1"],
    ["set", "modules.no_such_module", "true"],
    ["set", "modules", "true"],
    ["set", "old_file_days", "0"],
    ["set", "old_file_days", "-3"],
    ["set", "old_file_days", "1.5"],
    ["set", "old_file_days", "soon"],
    ["set", "storage_warn_gb", "nan"],
    ["set", "storage_warn_gb", "inf"],
    ["set", "old_file_days", "1", "2"],
    ["set", "permanent_delete", "yes"],
    ["set", "email_report_to", "not-an-address"],
    ["set", "email_report_to", "@"],
    ["set", "email_report_to", "a@b\x07"],
    ["set", "old_file_days", "100001"],
    ["set", "old_file_days", "9" * 400],
    ["set", "storage_urgent_gb", "30"],
    ["set", "storage_warn_gb", "5"],
    ["set", "scan_paths", "Downloads"],
    ["set", "scan_paths", ""],
    ["get", "no_such_key"],
    ["unset", "no_such_key"],
])
def test_bad_input_is_refused_and_nothing_written(cfg_file, argv, capsys):
    cfg_file.write_text('{"old_file_days": 90}')
    assert run(*argv) == 1
    assert cfg_file.read_text() == '{"old_file_days": 90}'
    assert capsys.readouterr().err.startswith("config: ")


@pytest.mark.parametrize("content", ['{"old_file_days": 90,', "[1]", '{"modules": []}'])
def test_damaged_file_is_never_overwritten(cfg_file, content, capsys):
    cfg_file.write_text(content)
    assert run("set", "modules.caches", "false") == 1
    assert cfg_file.read_text() == content
    assert str(cfg_file) in capsys.readouterr().err


@pytest.mark.parametrize("bad", [
    {"permanent_delete": "false"},
    {"modules": {"caches": "false"}},
    {"old_file_days": -1},
    {"scan_paths": "~/Downloads"},
])
def test_bad_value_already_in_the_file_blocks_set_but_can_be_unset(cfg_file, bad, capsys):
    cfg_file.write_text(json.dumps(bad))
    assert run("set", "log_retention_days", "3") == 1
    assert saved(cfg_file) == bad
    key = "modules.caches" if "modules" in bad else next(iter(bad))
    assert f"config unset {key}" in capsys.readouterr().err
    assert run("unset", key) == 0
    assert run("set", "log_retention_days", "3") == 0


@pytest.mark.parametrize("unrelated", ["old_file_days", "log_retention_days", "modules.caches"])
def test_unrelated_unset_does_not_rewrite_a_file_with_a_bad_value(cfg_file, unrelated):
    content = '{"permanent_delete": "false", "old_file_days": 90}'
    cfg_file.write_text(content)
    assert run("unset", unrelated) == 1
    assert cfg_file.read_text() == content


@pytest.mark.parametrize("data,key", [
    ({"permanent_delete": "false"}, "permanent_delete"),
    ({"modules": {"caches": "false"}}, "modules.caches"),
])
def test_show_and_get_flag_a_bad_value_instead_of_reading_it(cfg_file, data, key, capsys):
    cfg_file.write_text(json.dumps(data))
    assert run() == 0
    assert f'{key} = "false"  (INVALID: must be true or false)\n' in capsys.readouterr().out
    assert run("get", key) == 1
    out = capsys.readouterr()
    assert out.out == "" and "INVALID" in out.err


def test_two_bad_values_can_be_cleared_one_at_a_time(cfg_file):
    cfg_file.write_text(json.dumps({"permanent_delete": "false", "old_file_days": 0}))
    assert run("unset", "permanent_delete") == 0
    assert run("unset", "old_file_days") == 0
    assert saved(cfg_file) == {}


def test_set_can_correct_a_bad_value_and_keeps_unknown_keys(cfg_file):
    cfg_file.write_text(json.dumps({"permanent_delete": "false", "note": "mine"}))
    assert run("set", "permanent_delete", "false") == 0
    assert saved(cfg_file) == {"permanent_delete": False, "note": "mine"}


def test_unset_cannot_leave_urgent_above_warn(cfg_file):
    cfg_file.write_text('{"storage_warn_gb": 50, "storage_urgent_gb": 30}')
    assert run("unset", "storage_warn_gb") == 1
    assert saved(cfg_file)["storage_warn_gb"] == 50


def test_failed_replace_leaves_the_file_and_no_leftovers(cfg_file):
    cfg_file.write_text("{}")
    with patch("config_cli.os.replace", side_effect=OSError("disk full")):
        assert run("set", "old_file_days", "5") == 1
    assert cfg_file.read_text() == "{}"
    assert list(cfg_file.parent.iterdir()) == [cfg_file]


def test_unset_returns_a_setting_to_its_default(cfg_file):
    cfg_file.write_text(json.dumps({"old_file_days": 90, "modules": {"caches": False}}))
    assert run("unset", "old_file_days") == 0
    assert run("unset", "modules.caches") == 0
    assert saved(cfg_file) == {"modules": {}}
    assert config.get("old_file_days") == 180


def test_main_routes_config_without_scanning(cfg_file):
    argv = ["main.py", "config", "set", "modules.thermal", "false"]
    with patch.object(sys, "argv", argv), patch("main.run_scan") as scan, \
         pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0
    scan.assert_not_called()
    assert saved(cfg_file) == {"modules": {"thermal": False}}
