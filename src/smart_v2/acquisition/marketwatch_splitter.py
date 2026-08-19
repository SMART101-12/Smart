from __future__ import annotations

"""Split a raw TSETMC MarketWatch XLSX snapshot into symbol-level raw records.

The splitter is deliberately a raw-ingestion boundary. It only unwraps the
provider file, extracts the provider row fields, and writes symbol-level raw
JSON. It does not validate, normalize, score, or promote records.
"""

import gzip
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


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
        if not source.exists():
            raise FileNotFoundError(source)
        if not source_date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_date):
            raise ValueError("source_date must be YYYY-MM-DD")

        xlsx_bytes = gzip.decompress(source.read_bytes())
        rows = self._read_sheet(xlsx_bytes)
        instruments = self._extract_instruments(rows, source_date)

        written: list[Path] = []
        seen_paths: set[Path] = set()
        for item in instruments:
            target_dir = output_root / f"{item.symbol_en}_{item.ins_code}"
            target = target_dir / f"{source_date}.json"
            if target in seen_paths:
                raise ValueError(f"duplicate symbol/insCode output: {target}")
            seen_paths.add(target)
            target_dir.mkdir(parents=True, exist_ok=True)
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
                            "raw_preserved": True,
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
            ns = {"main": MAIN_NS}
            first_sheet = workbook.find("main:sheets/main:sheet", ns)
            if first_sheet is None:
                return []
            rel_id = first_sheet.attrib[f"{{{REL_NS}}}id"]
            rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rel = next(
                (r for r in rel_root if r.attrib.get("Id") == rel_id),
                None,
            )
            if rel is None:
                raise ValueError(f"worksheet relationship not found: {rel_id}")
            target = rel.attrib["Target"].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            root = ET.fromstring(archive.read(target))

            rows: list[list[str]] = []
            for row in root.findall(".//main:sheetData/main:row", ns):
                cells: dict[int, str] = {}
                max_col = -1
                for cell in row.findall("main:c", ns):
                    ref = cell.attrib.get("r", "")
                    col = self._column_index(ref)
                    if col < 0:
                        continue
                    cells[col] = self._cell_value(cell, shared)
                    max_col = max(max_col, col)
                values = [cells.get(i, "") for i in range(max_col + 1)]
                rows.append(values)
            return rows

    @staticmethod
    def _column_index(cell_ref: str) -> int:
        letters = "".join(ch for ch in cell_ref if ch.isalpha())
        if not letters:
            return -1
        result = 0
        for ch in letters.upper():
            result = result * 26 + (ord(ch) - 64)
        return result - 1

    @staticmethod
    def _cell_value(cell: ET.Element, shared: list[str]) -> str:
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            return "".join(t.text or "" for t in cell.findall(f".//{{{MAIN_NS}}}t"))
        value = cell.find(f"{{{MAIN_NS}}}v")
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
            "".join(t.text or "" for t in item.findall(f".//{{{MAIN_NS}}}t"))
            for item in root.findall(f".//{{{MAIN_NS}}}si")
        ]

    @staticmethod
    def _norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.strip().lower())

    def _find_header(self, rows: list[list[str]]) -> tuple[int, list[str]]:
        for row_index, row in enumerate(rows[:20]):
            headers = [str(v).strip() for v in row]
            normalized = {self._norm(v) for v in headers if v}
            has_ins = bool(normalized & {"inscode", "instrumentcode", "ins_code"})
            has_symbol = bool(
                normalized
                & {"symbolen", "symbolfa", "symbol", "l18", "lval18afc", "lval18"}
            )
            if has_ins and has_symbol:
                return row_index, headers
        raise ValueError("MarketWatch header row with InsCode and symbol fields was not found")

    def _extract_instruments(self, rows: list[list[str]], source_date: str) -> list[RawInstrument]:
        if not rows:
            return []
        header_index, headers = self._find_header(rows)
        index = {self._norm(name): i for i, name in enumerate(headers) if name}

        def get(row: list[str], *names: str) -> str:
            for name in names:
                i = index.get(self._norm(name))
                if i is not None and i < len(row):
                    return str(row[i]).strip()
            return ""

        result: list[RawInstrument] = []
        seen_codes: set[str] = set()
        for row in rows[header_index + 1 :]:
            ins_code = get(row, "InsCode", "inscode", "InstrumentCode")
            symbol_fa = get(row, "SymbolFa", "Symbol FA", "lVal18AFC", "l18", "Symbol", "name")
            symbol_en = get(row, "SymbolEn", "Symbol EN", "symbol_en")
            instrument_id = get(row, "InstrumentID", "InstrumentId", "iid")
            if not ins_code or not symbol_fa and not symbol_en:
                continue
            if not ins_code.isdigit() or ins_code in seen_codes:
                continue
            seen_codes.add(ins_code)

            # MarketWatch commonly exposes the Persian ticker only. Until a
            # separate symbol registry supplies an official Latin ticker, use
            # a deterministic English filesystem key based on the instrument
            # code rather than inventing a translation.
            if not symbol_en:
                symbol_en = f"INS_{ins_code}"

            fields = {
                headers[i]: row[i] if i < len(row) else ""
                for i in range(len(headers))
                if headers[i]
            }
            fields.setdefault("InstrumentID", instrument_id)
            result.append(RawInstrument(ins_code, symbol_en.upper(), symbol_fa, source_date, fields))
        return result
