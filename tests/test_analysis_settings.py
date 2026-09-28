import json

import pytest

from smart.analysis_settings import load_analysis_configuration


def test_configuration_is_frozen_and_invalid_weights_fail(monkeypatch, tmp_path):
    config = load_analysis_configuration()
    assert len(config["sha256"]) == 64
    config.pop("sha256")
    config["decision_weights"]["market"] = 200
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("SMART_ANALYSIS_CONFIG", str(path))
    with pytest.raises(ValueError, match="sum to 100"):
        load_analysis_configuration()
