import json
from unittest.mock import patch
import config


def test_load_config_returns_defaults(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"large_file_threshold_mb": 250}))
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.get("large_file_threshold_mb") == 250


def test_load_config_missing_key_uses_default(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.get("large_file_threshold_mb") == 500


def test_module_enabled(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"modules": {"caches": False}}))
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.module_enabled("caches") is False


def test_module_enabled_default_true(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.module_enabled("caches") is True


def test_the_committed_config_runs_the_downloads_clean():
    """CleanUp's 06:00 cron job was removed on 2026-11-27 (card 3yHbtDtc), so
    the Downloads module is the only thing clearing ~/Downloads. Switching it
    off in the shipped config would stop that silently."""
    import os
    shipped = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    with open(shipped) as f:
        assert json.load(f)["modules"]["downloads"] is True
