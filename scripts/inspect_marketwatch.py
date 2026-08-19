"""Inspect a raw TSETMC MarketWatch snapshot before symbol splitting."""
from __future__ import annotations

import argparse
import gzip
import io
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(t.text or "" for t in item.findall(".//main:t", NS))
        for item in root.findall("main:si", NS)
    ]


def cell_text(cell: ET.Element, shared: list[str]) -> str:
    if cell.attrib.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//main:t", NS))
    value = cell.find("main:v", NS)
    text = "" if value is None else value.text or ""
    if cell.attrib.get("t") == "s" and text:
        return shared[int(text)]
    return text


def col_index(ref: str) -> int | None:
    letters = "".join(ch for ch in ref if ch.isalpha())
    if not letters:
        return None
    value = 0
    for char in letters.upper():
        value = value * 26 + ord(char) - 64
    return value - 1


def read_rows(xlsx_bytes: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        shared = shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        sheet = workbook.find("main:sheets/main:sheet", NS)
        if sheet is None:
            return []
        rid = sheet.attrib[REL_ID]
        rel = next(r for r in rels if r.attrib.get("Id") == rid)
        target = rel.attrib["Target"].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        root = ET.fromstring(archive.read(target))
        rows: list[list[str]] = []
        for row in root.findall(".//main:sheetData/main:row", NS):
            cells: dict[int, str] = {}
            for cell in row.findall("main:c", NS):
                idx = col_index(cell.attrib.get("r", ""))
                if idx is not None:
                    cells[idx] = cell_text(cell, shared)
            max_idx = max(cells, default=-1)
            rows.append([cells.get(i, "") for i in range(max_idx + 1)])
        return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()

    raw = args.source.read_bytes()
    xlsx = gzip.decompress(raw)
    rows = read_rows(xlsx)

    print(f"SOURCE={args.source}")
    print(f"GZIP_BYTES={len(raw)}")
    print(f"XLSX_BYTES={len(xlsx)}")
    print(f"ROWS={len(rows)}")

    header_pos = None
    for pos, row in enumerate(rows[:30]):
        keys = {"".join(ch for ch in str(v).lower() if ch.isalnum()) for v in row if str(v).strip()}
        if "inscode" in keys:
            header_pos = pos
            print(f"HEADER_ROW={pos + 1}")
            print("HEADERS=" + " | ".join(str(v) for v in row if str(v).strip()))
            break

    if header_pos is None:
        print("HEADER_ROW=NOT_FOUND")
        return 2

    headers = [str(v).strip() for v in rows[header_pos]]
    normalized = {"".join(ch for ch in h.lower() if ch.isalnum()): i for i, h in enumerate(headers) if h}
    ins_idx = normalized.get("inscode")
    symbol_idx = normalized.get("symbol") or normalized.get("symbolfa") or normalized.get("l18")

    ins_codes: list[str] = []
    nonempty = 0
    nonascii_symbols = 0
    for row in rows[header_pos + 1 :]:
        ins = row[ins_idx].strip() if ins_idx is not None and ins_idx < len(row) else ""
        if not ins:
            continue
        nonempty += 1
        ins_codes.append(ins)
        if symbol_idx is not None and symbol_idx < len(row):
            symbol = row[symbol_idx].strip()
            if symbol and not symbol.isascii():
                nonascii_symbols += 1

    duplicates = nonempty - len(set(ins_codes))
    print(f"DATA_ROWS_WITH_INSCODE={nonempty}")
    print(f"UNIQUE_INSCODE={len(set(ins_codes))}")
    print(f"DUPLICATE_INSCODE={duplicates}")
    print(f"NONASCII_SYMBOLS={nonascii_symbols}")
    print("SAMPLE_INSCODES=" + ",".join(ins_codes[:10]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
