from __future__ import annotations

"""Split a raw TSETMC MarketWatch XLSX snapshot into symbol-level raw records.

The splitter is deliberately a raw-ingestion boundary: it does not validate,
normalize, score, or promote records into validated_market.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import gzip
import io
import json
import re
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

    _NS = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    _REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

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
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
            shared = self._shared_strings(archive)
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            first_sheet = workbook.find("main:sheets/main:sheet", self._NS)
            if first_sheet is None:
                return []

            rel_id = first_sheet.attrib[self._REL_ID]
            rel = next(r for r in rels if r.attrib.get("Id") == rel_id)
            target = rel.attrib["Target"].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            root = ET.fromstring(archive.read(target))

            rows: list[list[str]] = []
            for row in root.findall(".//main:sheetData/main:row", self._NS):
                cells: dict[int, str] = {}
                max_col = -1
                for cell in row.findall("main:c", self._NS):
                    ref = cell.attrib.get("r", "")
                    col = self._column_index(ref)
                    if col is None:
                        continue
                    cells[col] = self._cell_text(cell, shared)
                    max_col = max(max_col, col)
                rows.append([cells.get(i, "") for i in range(max_col + 1)])
            return rows

    @staticmethod
    def _column_index(ref: str) -> int | None:
        letters = "".join(ch for ch in ref if ch.isalpha())
        if not letters:
            return None
        value = 0
        for char in letters.upper():
            value = value * 26 + (ord(char) - 64)
        return value - 1

    @staticmethod
    def _cell_text(cell: ET.Element, shared: list[str]) -> str:
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            return "".join(t.text or "" for t in cell.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
        value = cell.find("main:v", MarketWatchSplitter._NS)
        text = "" if value is None else value.text or ""
        if cell_type == "s" and text:
            index = int(text)
            return shared[index] if 0 <= index < len(shared) else ""
        return text

    def _shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        try:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        return [
            "".join(t.text or "" for t in item.findall(".//main:t", self._NS))
            for item in root.findall("main:si", self._NS)
        ]

    def _extract_instruments(self, rows: list[list[str]], source_date: str) -> list[RawInstrument]:
        header_pos = self._find_header(rows)
        if header_pos is None:
            return []

        headers = [str(v).strip() for v in rows[header_pos]]
        index = {self._header_key(name): i for i, name in enumerate(headers) if name}

        def get(row: list[str], *names: str) -> str:
            for name in names:
                i = index.get(self._header_key(name))
                if i is not None and i < len(row):
                    return str(row[i]).strip()
            return ""

        result: list[RawInstrument] = []
        seen: set[str] = set()
        for row in rows[header_pos + 1 :]:
            ins_code = get(row, "InsCode", "inscode", "ins code")
            if not ins_code or ins_code in seen:
                continue

            symbol_fa = get(row, "SymbolFa", "Symbol FA", "l18", "symbol")
            raw_symbol = get(row, "SymbolEn", "Symbol EN", "EnglishSymbol", "symbol_en")
            symbol_en = self._safe_symbol_en(raw_symbol, ins_code)
            if not symbol_fa:
                symbol_fa = raw_symbol
            if not symbol_en:
                continue

            fields = {
                headers[i]: row[i] if i < len(row) else ""
                for i in range(len(headers))
                if headers[i]
            }
            result.append(RawInstrument(ins_code, symbol_en, symbol_fa, source_date, fields))
            seen.add(ins_code)
        return result

    @staticmethod
    def _find_header(rows: list[list[str]]) -> int | None:
        for pos, row in enumerate(rows[:30]):
            normalized = {MarketWatchSplitter._header_key(str(v)) for v in row if str(v).strip()}
            if "inscode" in normalized and ({"symbolen", "symbol"} & normalized or "l18" in normalized):
                return pos
        return None

    @staticmethod
    def _header_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.strip().lower())

    @staticmethod
    def _safe_symbol_en(value: str, ins_code: str) -> str:
        value = value.strip()
        if value and all(ch.isascii() and (ch.isalnum() or ch in "_-" ) for ch in value):
            return value.upper()
        return f"INS_{ins_code}"
