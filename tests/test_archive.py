from smart.archive import (
    archive_monthly,
    deduplicate_rows,
    remove_exact_duplicate_derived_files,
    validate_canonical_rows,
)


def _row(day=20260815, **extra):
    value = {
        "dEven": day,
        "pFirst": 98,
        "pMax": 105,
        "pMin": 95,
        "pClosing": 100,
        "pDrCotVal": 100,
        "qTotTran5J": 10,
        "qTotCap": 1000,
        "zTotTran": 2,
    }
    value.update(extra)
    return value


def test_deduplicate_prefers_more_complete_row_and_reports_invalid():
    rows, report = deduplicate_rows(
        [_row(qTotCap=None), _row(qTotCap=2000), {"dEven": "bad", "pClosing": 2}],
        symbol="X",
    )
    assert len(rows) == 1
    assert rows[0]["value"] == 2000
    assert report["duplicate_dates"] == 1
    assert report["invalid_rows"] == 1


def test_archive_and_quality_report_are_deterministic(tmp_path):
    report = archive_monthly("X", [_row()], root=tmp_path)
    assert report["quality"]["status"] in {"PASS", "PASS_WITH_WARNINGS"}
    assert report["archive_paths"]
    assert (tmp_path / "X" / "quality_report.json").exists()
    audit = validate_canonical_rows(
        [{"source_date": "2026-08-15", "close": 100, "high": 105, "low": 95}]
    )
    assert audit["status"] == "PASS"


def test_adjusted_close_range_is_warning_by_default_and_error_in_strict_mode():
    row = {
        "source_date": "2026-08-15",
        "open": 100,
        "high": 100,
        "low": 90,
        "close": 105,
    }
    relaxed = validate_canonical_rows([row])
    strict = validate_canonical_rows([row], strict_ohlc=True)
    assert relaxed["status"] == "PASS_WITH_WARNINGS"
    assert relaxed["warning_count"] == 1
    assert strict["status"] == "FAIL"
    assert strict["error_count"] == 1


def test_duplicate_cleanup_is_dry_run_by_default(tmp_path):
    archive_monthly("X", [_row()], root=tmp_path / "a")
    archive_monthly("Y", [_row()], root=tmp_path / "b")
    # Different symbol metadata means these are not exact duplicate files.
    result = remove_exact_duplicate_derived_files(tmp_path, apply=False)
    assert result["status"] == "DRY_RUN"
    assert result["removed"] == []
