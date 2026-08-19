import gzip
import io
import zipfile
from pathlib import Path

from smart_v2.acquisition.marketwatch_splitter import MarketWatchSplitter


def _xlsx_bytes() -> bytes:
    files = {
        "xl/workbook.xml": '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="MarketWatch" sheetId="1" r:id="rId1"/></sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''',
        "xl/worksheets/sheet1.xml": '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
            <row><c><v>InsCode</v></c><c><v>SymbolEn</v></c><c><v>SymbolFa</v></c><c><v>Close</v></c></row>
            <row><c><v>123</v></c><c><v>TEST</v></c><c><v>آزمایشی</v></c><c><v>100</v></c></row>
        </sheetData></worksheet>''',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_marketwatch_splitter_preserves_raw_boundary(tmp_path: Path):
    source = tmp_path / "2026-08-19.gz"
    source.write_bytes(gzip.compress(_xlsx_bytes()))

    output = tmp_path / "symbols"
    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 1
    assert written[0].as_posix().endswith("TEST_123/2026-08-19.json")
    text = written[0].read_text(encoding="utf-8")
    assert '"dataset_type": "RAW_MARKETWATCH"' in text
    assert '"symbol_fa": "آزمایشی"' in text
    assert '"Close": "100"' in text
