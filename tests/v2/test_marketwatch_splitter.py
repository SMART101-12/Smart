import gzip
import io
import json
import zipfile
from pathlib import Path

import pytest

from smart_v2.acquisition.marketwatch_splitter import MarketWatchSplitter


def _xlsx_bytes() -> bytes:
    files = {
        "xl/workbook.xml": '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="MarketWatch" sheetId="1" r:id="rId1"/></sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''',
        "xl/worksheets/sheet1.xml": '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
            <row r="1"><c r="A1"><v>MarketWatch snapshot</v></c></row>
            <row r="2"><c r="A2"><v>provider header</v></c></row>
            <row r="3"><c r="A3"><v>InsCode</v></c><c r="B3"><v>SymbolEn</v></c><c r="C3"><v>SymbolFa</v></c><c r="D3"><v>Close</v></c></row>
            <row r="4"><c r="A4"><v>123</v></c><c r="B4"><v>TEST</v></c><c r="C4" t="inlineStr"><is><t>آزمایشی</t></is></c><c r="D4"><v>100</v></c></row>
            <row r="5"><c r="A5"><v>456</v></c><c r="C5" t="inlineStr"><is><t>فولاد</t></is></c><c r="D5"><v>200</v></c></row>
            <row r="6"><c r="A6"><v>456</v></c><c r="C6" t="inlineStr"><is><t>فولاد</t></is></c><c r="D6"><v>201</v></c></row>
        </sheetData></worksheet>''',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _shared_xlsx_bytes() -> bytes:
    files = {
        "xl/workbook.xml": '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="MarketWatch" sheetId="1" r:id="rId1"/></sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''',
        "xl/sharedStrings.xml": '''<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>InsCode</t></si><si><t>Symbol</t></si><si><t>Close</t></si><si><t>789</t></si><si><t>SHARED</t></si><si><t>300</t></si></sst>''',
        "xl/worksheets/sheet1.xml": '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
            <row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
            <row><c r="A2" t="s"><v>3</v></c><c r="B2" t="s"><v>4</v></c><c r="C2" t="s"><v>5</v></c></row>
        </sheetData></worksheet>''',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_marketwatch_splitter_handles_realistic_header_layout_and_sparse_cells(tmp_path: Path):
    source = tmp_path / "2026-08-19.gz"
    source.write_bytes(gzip.compress(_xlsx_bytes()))

    output = tmp_path / "symbols"
    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 2
    assert written[0].name == "2026-08-19.json"
    assert {path.parent.name for path in written} == {"TEST_123", "INS_456_456"}

    test_record = json.loads((output / "TEST_123" / "2026-08-19.json").read_text(encoding="utf-8"))
    assert test_record["dataset_type"] == "RAW_MARKETWATCH"
    assert test_record["source"]["raw_preserved"] is True
    assert test_record["instrument"]["symbol_fa"] == "آزمایشی"
    assert test_record["raw"]["Close"] == "100"


def test_marketwatch_splitter_reads_shared_strings(tmp_path: Path):
    source = tmp_path / "shared.gz"
    source.write_bytes(gzip.compress(_shared_xlsx_bytes()))
    written = MarketWatchSplitter().split(source, tmp_path / "symbols", "2026-08-19")

    assert len(written) == 1
    record = json.loads(written[0].read_text(encoding="utf-8"))
    assert record["instrument"]["ins_code"] == "789"
    assert record["instrument"]["symbol_en"] == "SHARED"
    assert record["raw"]["Close"] == "300"


def test_marketwatch_splitter_rejects_invalid_date(tmp_path: Path):
    source = tmp_path / "2026-08-19.gz"
    source.write_bytes(gzip.compress(_xlsx_bytes()))
    with pytest.raises(ValueError):
        MarketWatchSplitter().split(source, tmp_path / "symbols", "19-08-2026")
