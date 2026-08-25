from __future__ import annotations

"""Split a raw TSETMC MarketWatch XLSX snapshot into InsCode-keyed raw records."""

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
    symbol_fa: str
    source_date: str
    fields: dict[str, Any]
    row_number: int
    ins_code: str
    symbol_en: str | None = None


class MarketWatchSplitter:
    """Read a gzip-wrapped XLSX MarketWatch snapshot without mutating source data.

    Path identity is exclusively ``ins_code``. Symbol names are metadata only.
    Output layout: <output_root>/<ins_code>/YYYY-MM/YYYY-MM-DD.json
    """

    _NS = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    _REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    def split(self, source: Path, output_root: Path, source_date: str) -> list[Path]:
        raw = source.read_bytes()
        if raw[:2] != b"\x1f\x8b":
            raise ValueError(f"Expected gzip MarketWatch snapshot: {source}")
        rows = self._read_sheet(gzip.decompress(raw))
        instruments = self._extract_instruments(rows, source_date)

        written: list[Path] = []
        for item in instruments:
            target = output_root / item.ins_code / source_date[:7] / f"{source_date}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "dataset_type": "RAW_MARKETWATCH",
                        "instrument": {
                            "ins_code": item.ins_code,
                            "symbol_fa": item.symbol_fa,
                            "symbol_en": item.symbol_en,
                        },
                        "source": {
                            "type": "tsetmc_marketwatch",
                            "source_file": str(source),
                            "snapshot_date": item.source_date,
                            "source_row": item.row_number,
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
            rel_id = first_sheet.attrib.get(self._REL_ID)
            rel = next((r for r in rels if r.attrib.get("Id") == rel_id), None)
            if rel is None:
                return []
            target = rel.attrib["Target"].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            root = ET.fromstring(archive.read(target))
            rows: list[list[str]] = []
            for row in root.findall(".//main:sheetData/main:row", self._NS):
                cells: dict[int, str] = {}
                max_col = -1
                for cell in row.findall("main:c", self._NS):
                    col = self._column_index(cell.attrib.get("r", ""))
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
            value = value * 26 + ord(char) - 64
        return value - 1

    @staticmethod
    def _cell_text(cell: ET.Element, shared: list[str]) -> str:
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            return "".join(
                t.text or ""
                for t in cell.findall(
                    ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                )
            )
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
        symbol_fa_index = self._find_symbol_fa_index(headers)
        ins_code_index = self._find_ins_code_index(headers)
        symbol_en_index = self._find_symbol_en_index(headers)
        if symbol_fa_index is None or ins_code_index is None:
            return []

        result: list[RawInstrument] = []
        seen_ins_codes: set[str] = set()
        for row_number, row in enumerate(rows[header_pos + 1 :], start=header_pos + 2):
            if symbol_fa_index >= len(row) or ins_code_index >= len(row):
                continue
            symbol_fa = self._clean_symbol(row[symbol_fa_index])
            ins_code = str(row[ins_code_index]).strip()
            if not symbol_fa or not ins_code:
                continue
            if ins_code in seen_ins_codes:
                continue
            seen_ins_codes.add(ins_code)
            symbol_en = None
            if symbol_en_index is not None and symbol_en_index < len(row):
                symbol_en = self._clean_symbol(row[symbol_en_index]) or None
            fields = {
                headers[i]: row[i] if i < len(row) else ""
                for i in range(len(headers))
                if headers[i]
            }
            result.append(
                RawInstrument(
                    symbol_fa=symbol_fa,
                    symbol_en=symbol_en,
                    source_date=source_date,
                    fields=fields,
                    row_number=row_number,
                    ins_code=ins_code,
                )
            )
        return result

    @classmethod
    def _find_header(cls, rows: list[list[str]]) -> int | None:
        for pos, row in enumerate(rows[:100]):
            headers = [str(v).strip() for v in row]
            if cls._find_ins_code_index(headers) is not None and cls._find_symbol_fa_index(headers) is not None:
                return pos
        return None

    @staticmethod
    def _normalize_header(value: str) -> str:
        return re.sub(r"\s+", "", str(value).strip().lower()).replace("\u200c", "")

    @classmethod
    def _find_symbol_fa_index(cls, headers: list[str]) -> int | None:
        preferred = {"symbolfa", "نماد", "lval18", "l18", "lval18afc", "symbol"}
        for i, value in enumerate(headers):
            normalized = cls._normalize_header(value)
            if normalized in preferred or "نماد" in normalized:
                return i
        return None

    @classmethod
    def _find_symbol_en_index(cls, headers: list[str]) -> int | None:
        preferred = {"symbolen"}
        for i, value in enumerate(headers):
            if cls._normalize_header(value) in preferred:
                return i
        return None

    @classmethod
    def _find_ins_code_index(cls, headers: list[str]) -> int | None:
        preferred = {"inscode", "inscodevalue", "inscodeid", "instrumentcode"}
        for i, value in enumerate(headers):
            if cls._normalize_header(value) in preferred:
                return i
        return None

    @staticmethod
    def _clean_symbol(value: str) -> str:
        return str(value or "").strip().replace("\u200c", "")
