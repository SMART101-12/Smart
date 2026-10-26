"""Atomic persistence of symbol profiles (regression for partial-write corruption)."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from smart.symbol_learning import _persist, load_latest_symbol_profile


def test_persist_writes_artifact_and_latest(tmp_path):
    profile = {"symbol": "فولاد", "status": "OK"}
    result = _persist(profile, tmp_path)
    latest = Path(result["latest_artifact_path"])
    artifact = Path(result["artifact_path"])
    assert json.loads(latest.read_text(encoding="utf-8"))["symbol"] == "فولاد"
    assert json.loads(artifact.read_text(encoding="utf-8"))["symbol"] == "فولاد"
    assert load_latest_symbol_profile("فولاد", tmp_path)["status"] == "OK"


def test_persist_leaves_no_temp_files(tmp_path):
    _persist({"symbol": "X", "status": "OK"}, tmp_path)
    leftovers = list((tmp_path / "X" / "symbol_profiles").glob("*.tmp"))
    assert leftovers == []


def test_load_latest_survives_corrupt_file(tmp_path):
    path = tmp_path / "X" / "symbol_profiles"
    path.mkdir(parents=True)
    (path / "latest.json").write_text("{corrupt", encoding="utf-8")
    assert load_latest_symbol_profile("X", tmp_path) is None


def test_interrupted_latest_write_preserves_previous_profile(monkeypatch, tmp_path):
    old = _persist({"symbol": "X", "status": "OLD"}, tmp_path)
    latest = Path(old["latest_artifact_path"])
    original = Path.write_text

    def interrupted(path, data, *args, **kwargs):
        if path.name.startswith("latest.json."):
            original(path, data[:10], *args, **kwargs)
            assert load_latest_symbol_profile("X", tmp_path)["status"] == "OLD"
            raise OSError("disk write interrupted")
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        _persist({"symbol": "X", "status": "NEW"}, tmp_path)
    assert json.loads(latest.read_text(encoding="utf-8"))["status"] == "OLD"
    assert not list(latest.parent.glob("*.tmp"))


def test_concurrent_profiles_publish_complete_archived_versions(tmp_path):
    def persist(index):
        return _persist({"symbol": "X", "status": "OK", "index": index,
                         "payload": "x" * 10000}, tmp_path)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(persist, range(20)))
    latest = load_latest_symbol_profile("X", tmp_path)
    assert latest in results
    for result in results:
        assert json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8")) == result
    assert not list(tmp_path.rglob("*.tmp"))


def test_invalid_numeric_profile_never_replaces_valid_latest(tmp_path):
    _persist({"symbol": "X", "score": 12}, tmp_path)
    with pytest.raises(ValueError):
        _persist({"symbol": "X", "score": float("nan")}, tmp_path)
    assert load_latest_symbol_profile("X", tmp_path)["score"] == 12
