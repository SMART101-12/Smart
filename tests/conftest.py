"""Keep deterministic research tests independent of the user's persisted cache."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_research_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMART_RESEARCH_CACHE", str(tmp_path / "research_cache"))
