from __future__ import annotations

"""Split a raw TSETMC MarketWatch XLSX snapshot into symbol-level raw records.

MarketWatchPlus exports a gzip-wrapped XLSX whose public market-watch sheet does
not contain InsCode or an English symbol. This stage therefore uses the Persian
symbol as the source identity and creates an ASCII-only stable directory key.
InsCode/ISIN enrichment remains a later acquisition step.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import gzip
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class RawInstrument:
    symbol_fa: str
    symbol_key: str
    source_date: str
    fields: dict[str, Any]
    row_number: int


class MarketWatchSplitter:
    """Read a gzip-wrapped XLSX MarketWatch snapshot without mutating source data."""

    _NS = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    _REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    def split(self, source: Path, output_root: Path, source_date: str) -> list[Path]:
        raw = source.read_bytes()
        if raw[:2] != b"\x1f\x8b":
            raise ValueError(f"Expected gzip MarketWatch snapshot: {source}")

        xlsx_bytes = gzip.decompress(raw)
        rows = self._read_sheet(xlsx_bytes)
        instruments = self._extract_instruments(rows, source_date)

        written: list[Path] = []
        duplicate_counts: dict[str, int] = {}
        for item in instruments:
            duplicate_counts[item.symbol_fa] = duplicate_counts.get(item.symbol_fa, 0) + 1

        seen: dict[str, int] = {}
        for item in instruments:
            seen[item.symbol_fa] = seen.get(item.symbol_fa, 0) + 1
            suffix = "" if duplicate_counts[item.symbol_fa] == 1 else f"_{seen[item.symbol_fa]}"
            folder_key = item.symbol_key + suffix
            target_dir = output_root / folder_key
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source_date[:7] / f"{source_date}.json"
            target.write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "dataset_type": "RAW_MARKETWATCH",
                        "instrument": {
                            "symbol_fa": item.symbol_fa,
                            "symbol_key": folder_key,
                            "ins_code": None,
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
            if not rel_id:
                return []
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
        symbol_index = next(
            (i for i, value in enumerate(headers) if self._is_symbol_header(value)),
            None,
        )
        if symbol_index is None:
            return []

        result: list[RawInstrument] = []
        seen_rows: set[str] = set()
        for row_offset, row in enumerate(rows[header_pos + 1 :], start=header_pos + 2):
            if symbol_index >= len(row):
                continue
            symbol_fa = self._clean_symbol(row[symbol_index])
            if not symbol_fa:
                continue

            fields = {
                headers[i]: row[i] if i < len(row) else ""
                for i in range(len(headers))
                if headers[i]
            }
            fingerprint = json.dumps(fields, ensure_ascii=False, sort_keys=True)
            if fingerprint in seen_rows:
                continue
            seen_rows.add(fingerprint)

            result.append(
                RawInstrument(
                    symbol_fa=symbol_fa,
                    symbol_key=self._symbol_key(symbol_fa),
                    source_date=source_date,
                    fields=fields,
                    row_number=row_offset,
                )
            )
        return result

    @staticmethod
    def _find_header(rows: list[list[str]]) -> int | None:
        for pos, row in enumerate(rows[:50]):
            nonempty = [str(v).strip() for v in row if str(v).strip()]
            if len(nonempty) >= 5 and any(MarketWatchSplitter._is_symbol_header(v) for v in nonempty):
                return pos
        return None

    @staticmethod
    def _is_symbol_header(value: str) -> bool:
        normalized = re.sub(r"\s+", "", value.strip().lower()).replace("\u200c", "")
        return normalized in {"نماد", "symbol", "lval18", "l18", "lval18afc"} or "نماد" in normalized

    @staticmethod
    def _clean_symbol(value: str) -> str:
        return str(value or "").strip().replace("\u200c", "")

    @staticmethod
    def _symbol_key(symbol_fa: str) -> str:
        digest = hashlib.sha1(symbol_fa.encode("utf-8")).hexdigest()[:12].upper()
        return f"SYMBOL_{digest}"
