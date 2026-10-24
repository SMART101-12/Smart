from typing import Any

import pytest

from smart.unified_analysis import _stage_status


@pytest.mark.parametrize("status", ["insufficient_data", "Insufficient verified data",
                                   "FAILED", "INVALID", "UNVERIFIED", "unexpected"])
def test_incomplete_or_unknown_result_is_never_completed(status: str) -> None:
    assert _stage_status({"status": status}) == "PARTIAL"


@pytest.mark.parametrize("value", [{"status": "VERIFIED"}, {"status": "ready"},
                                  {"status": "no_setup"}, {"insCode": "123"}])
def test_valid_stage_results(value: dict[str, Any]) -> None:
    assert _stage_status(value) == "COMPLETED"


def test_absent_result_is_not_available() -> None:
    assert _stage_status(None) == "NOT_AVAILABLE"
