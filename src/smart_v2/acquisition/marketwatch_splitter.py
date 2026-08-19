from __future__ import annotations

"""Split a raw TSETMC MarketWatch XLSX snapshot into symbol-level raw records.

The splitter is deliberately a raw-ingestion boundary: it does not validate,
normalize, score, or promote records into validated_market.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import gzip
import json
import zipfile
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class RawInstrument:
    ins_code: str
    symbol_en: str
    symbol_fa: str
    source_date: str
    fields: dict[str, Any]


class MarketWatchSplitter:
    """Read a gzip-wrapped XLSX MarketWatch snapshot without mutating source data."""

    def split(self, source: Path, output_root: Path, source_date: str) -> list[Path]:
        xlsx_bytes = gzip.decompress(source.read_bytes())
        rows = self._read_sheet(xlsx_bytes)
        instruments = self._extract_instruments(rows, source_date)

        written: list[Path] = []
        for item in instruments:
            target_dir = output_root / f"{item.symbol_en}_{item.ins_code}"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{source_date}.json"
            target.write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "dataset_type": "RAW_MARKETWATCH",
                        "instrument": {
                            "symbol_en": item.symbol_en,
                            "symbol_fa": item.symbol_fa,
                            "ins_code": item.ins_code,
                        },
                        "source": {
                            "type": "tsetmc_marketwatch",
                            "snapshot_date": item.source_date,
                        },
                        "raw": item.fields,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            written.append(target)
        return written

    def _read_sheet(self, xlsx_bytes: bytes) -> list[list[str]]:
        with zipfile.ZipFile(__import__("io").BytesIO(xlsx_bytes)) as archive:
            shared = self._shared_strings(archive)
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            ns = {
                "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
            }
            first_sheet = workbook.find("main:sheets/main:sheet", ns)
            if first_sheet is None:
                return []
            rel_id = first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            rel = next(
                r for r in rels
                if r.attrib.get("Id") == rel_id
            )
            target = rel.attrib["Target"].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            root = ET.fromstring(archive.read(target))

            rows: list[list[str]] = []
            for row in root.findall(".//main:sheetData/main:row", ns):
                values: list[str] = []
                for cell in row.findall("main:c", ns):
                    value = cell.find("main:v", ns)
                    text = "" if value is None else value.text or ""
                    if cell.attrib.get("t") == "s" and text:
                        text = shared[int(text)]
                    values.append(text)
                rows.append(values)
            return rows

    def _shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        try:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        return ["".join(t.text or "" for t in item.findall(".//main:t", ns)) for item in root.findall("main:si", ns)]

    def _extract_instruments(self, rows: list[list[str]], source_date: str) -> list[RawInstrument]:
        if not rows:
            return []
        headers = [str(v).strip() for v in rows[0]]
        index = {name.lower(): i for i, name in enumerate(headers) if name}

        def get(row: list[str], *names: str) -> str:
            for name in names:
                i = index.get(name.lower())
                if i is not None and i < len(row):
                    return str(row[i]).strip()
            return ""

        result: list[RawInstrument] = []
        for row in rows[1:]:
            ins_code = get(row, "InsCode", "inscode", "ins code")
            symbol_en = get(row, "SymbolEn", "Symbol EN", "symbol")
            symbol_fa = get(row, "SymbolFa", "Symbol FA", "name")
            if not ins_code or not symbol_en:
                continue
            fields = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers)) if headers[i]}
            result.append(RawInstrument(ins_code, symbol_en, symbol_fa, source_date, fields))
        return result
