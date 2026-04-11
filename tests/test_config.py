import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

def test_load_config_returns_defaults(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"large_file_threshold_mb": 250}))
    from importlib import reload
    import config
    reload(config)
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.get("large_file_threshold_mb") == 250

def test_load_config_missing_key_uses_default(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")
    from importlib import reload
    import config
    reload(config)
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.get("large_file_threshold_mb") == 500

def test_module_enabled(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"modules": {"caches": False}}))
    from importlib import reload
    import config
    reload(config)
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.module_enabled("caches") is False

def test_module_enabled_default_true(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")
    from importlib import reload
    import config
    reload(config)
    with patch("config.CONFIG_PATH", str(cfg_file)):
        config._reset()
        assert config.module_enabled("caches") is True
