import gzip
import io
import json
import zipfile
from pathlib import Path

from smart_v2.acquisition.marketwatch_splitter import MarketWatchSplitter


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _xlsx_bytes(sheet_xml: str, shared_strings: str | None = None) -> bytes:
    files = {
        "xl/workbook.xml": '<workbook xmlns="%s" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="MarketWatch" sheetId="1" r:id="rId1"/></sheets></workbook>' % NS,
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    if shared_strings is not None:
        files["xl/sharedStrings.xml"] = shared_strings
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _write_snapshot(tmp_path: Path, xlsx: bytes) -> tuple[Path, Path]:
    source = tmp_path / "2026-08-19.gz"
    source.write_bytes(gzip.compress(xlsx))
    return source, tmp_path / "symbols"


def test_marketwatch_splitter_preserves_raw_boundary(tmp_path: Path):
    xlsx = _xlsx_bytes(f'''<worksheet xmlns="{NS}"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>InsCode</t></is></c><c r="B1" t="inlineStr"><is><t>SymbolEn</t></is></c><c r="C1" t="inlineStr"><is><t>SymbolFa</t></is></c><c r="D1" t="inlineStr"><is><t>Close</t></is></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>123</t></is></c><c r="B2" t="inlineStr"><is><t>TEST</t></is></c><c r="C2" t="inlineStr"><is><t>آزمایشی</t></is></c><c r="D2"><v>100</v></c></row>
    </sheetData></worksheet>''')
    source, output = _write_snapshot(tmp_path, xlsx)

    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 1
    assert written[0].as_posix().endswith("SYMBOL_747B057B1C4C/2026-08/2026-08-19.json")
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["dataset_type"] == "RAW_MARKETWATCH"
    assert payload["instrument"]["symbol_fa"] == "آزمایشی"
    assert payload["instrument"]["ins_code"] is None
    assert payload["raw"]["Close"] == "100"


def test_sparse_cells_are_aligned_by_excel_reference(tmp_path: Path):
    xlsx = _xlsx_bytes(f'''<worksheet xmlns="{NS}"><sheetData>
        <row r="4"><c r="A4" t="inlineStr"><is><t>InsCode</t></is></c><c r="C4" t="inlineStr"><is><t>Symbol</t></is></c><c r="E4" t="inlineStr"><is><t>Close</t></is></c></row>
        <row r="5"><c r="A5"><v>456</v></c><c r="C5" t="inlineStr"><is><t>فولاد</t></is></c><c r="E5"><v>200</v></c></row>
    </sheetData></worksheet>''')
    source, output = _write_snapshot(tmp_path, xlsx)

    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 1
    assert written[0].as_posix().endswith("SYMBOL_FC1D3C950536/2026-08/2026-08-19.json")
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["instrument"]["symbol_fa"] == "فولاد"
    assert payload["raw"]["Close"] == "200"


def test_header_can_appear_after_metadata_rows(tmp_path: Path):
    xlsx = _xlsx_bytes(f'''<worksheet xmlns="{NS}"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t>MarketWatch</t></is></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>Snapshot</t></is></c></row>
        <row r="3"><c r="A3" t="inlineStr"><is><t>InsCode</t></is></c><c r="B3" t="inlineStr"><is><t>SymbolEn</t></is></c><c r="C3" t="inlineStr"><is><t>SymbolFa</t></is></c></row>
        <row r="4"><c r="A4"><v>789</v></c><c r="B4" t="inlineStr"><is><t>TEST2</t></is></c><c r="C4" t="inlineStr"><is><t>آزمایش۲</t></is></c></row>
    </sheetData></worksheet>''')
    source, output = _write_snapshot(tmp_path, xlsx)

    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 1
    assert written[0].as_posix().endswith("SYMBOL_476B5EED9793/2026-08/2026-08-19.json")


def test_shared_strings_and_duplicate_ins_code(tmp_path: Path):
    shared = f'''<sst xmlns="{NS}"><si><t>InsCode</t></si><si><t>SymbolEn</t></si><si><t>SymbolFa</t></si><si><t>TEST3</t></si><si><t>نمونه</t></si></sst>'''
    xlsx = _xlsx_bytes(f'''<worksheet xmlns="{NS}"><sheetData>
        <row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
        <row><c r="A2"><v>999</v></c><c r="B2" t="s"><v>3</v></c><c r="C2" t="s"><v>4</v></c></row>
        <row><c r="A3"><v>999</v></c><c r="B3" t="s"><v>3</v></c><c r="C3" t="s"><v>4</v></c></row>
    </sheetData></worksheet>''', shared)
    source, output = _write_snapshot(tmp_path, xlsx)

    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 1
    assert written[0].as_posix().endswith("SYMBOL_8E687366D567/2026-08/2026-08-19.json")


def test_non_ascii_symbol_en_uses_english_safe_directory_key(tmp_path: Path):
    xlsx = _xlsx_bytes(f'''<worksheet xmlns="{NS}"><sheetData>
        <row><c r="A1" t="inlineStr"><is><t>InsCode</t></is></c><c r="B1" t="inlineStr"><is><t>Symbol</t></is></c></row>
        <row><c r="A2"><v>321</v></c><c r="B2" t="inlineStr"><is><t>پالایش</t></is></c></row>
    </sheetData></worksheet>''')
    source, output = _write_snapshot(tmp_path, xlsx)

    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 1
    assert written[0].as_posix().endswith("SYMBOL_D498D640884A/2026-08/2026-08-19.json")


def test_real_marketwatch_persian_header_shape(tmp_path: Path):
    xlsx = _xlsx_bytes(f'''<worksheet xmlns="{NS}"><sheetData>
        <row r="1"><c r="A1" t="inlineStr"><is><t> </t></is></c></row>
        <row r="2"><c r="A2" t="inlineStr"><is><t>دیده بان بازار : 1405/05/28 - زمان آخرین معامله : 12:32:25</t></is></c></row>
        <row r="3"><c r="A3" t="inlineStr"><is><t>نماد</t></is></c><c r="B3" t="inlineStr"><is><t>نام</t></is></c><c r="C3" t="inlineStr"><is><t>تعداد</t></is></c><c r="D3" t="inlineStr"><is><t>حجم</t></is></c><c r="E3" t="inlineStr"><is><t>ارزش</t></is></c><c r="F3" t="inlineStr"><is><t>دیروز</t></is></c><c r="G3" t="inlineStr"><is><t>اولین</t></is></c><c r="H3" t="inlineStr"><is><t>آخرین معامله - مقدار</t></is></c></row>
        <row r="4"><c r="A4" t="inlineStr"><is><t>فولاد</t></is></c><c r="B4" t="inlineStr"><is><t>فولاد مبارکه اصفهان</t></is></c><c r="C4"><v>100</v></c><c r="D4"><v>2000</v></c><c r="E4"><v>300000</v></c><c r="F4"><v>4000</v></c><c r="G4"><v>4100</v></c><c r="H4"><v>4200</v></c></row>
    </sheetData></worksheet>''')
    source, output = _write_snapshot(tmp_path, xlsx)

    written = MarketWatchSplitter().split(source, output, "2026-08-19")

    assert len(written) == 1
    assert written[0].as_posix().endswith("SYMBOL_FC1D3C950536/2026-08/2026-08-19.json")
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["instrument"]["symbol_fa"] == "فولاد"
    assert payload["instrument"]["ins_code"] is None
    assert payload["raw"]["نام"] == "فولاد مبارکه اصفهان"
    assert payload["raw"]["آخرین معامله - مقدار"] == "4200"
