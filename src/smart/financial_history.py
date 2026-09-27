"""Persisted, versioned financial evidence. Analysis reads this repository only.

SMART DATA INTEGRITY RULE: KODAL is financial truth; TSETMC is market truth.
Never fabricate, estimate, interpolate or replace missing values with zero.
Reuse downloaded evidence and synchronize only new or missing documents/dates.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .snapshot_store import SnapshotStore


METRICS = {
    "revenue": "درآمد عملیاتی", "cost_of_revenue": "بهای تمام شده",
    "gross_profit": "سود ناخالص", "selling_expenses": "هزینه های فروش اداری و عمومی",
    "operating_profit": "سود عملیاتی", "finance_cost": "هزینه های مالی",
    "pretax_profit": "سود قبل از مالیات", "tax": "مالیات", "net_profit": "سود خالص",
    "eps": "سود هر سهم", "current_assets": "دارایی های جاری",
    "noncurrent_assets": "دارایی های غیرجاری", "assets": "جمع دارایی ها",
    "current_liabilities": "بدهی های جاری", "noncurrent_liabilities": "بدهی های غیرجاری",
    "liabilities": "جمع بدهی ها", "equity": "حقوق صاحبان سهام", "capital": "سرمایه",
    "operating_cash_flow": "جریان نقد عملیاتی", "investing_cash_flow": "جریان نقد سرمایه گذاری",
    "financing_cash_flow": "جریان نقد تامین مالی", "cash_change": "تغییرات نقد و معادل نقد",
    "shares": "تعداد سهام", "dividends": "سود تقسیمی", "dps": "DPS",
    "production": "تولید", "sales": "فروش", "sales_quantity": "مقدار فروش",
    "sales_rate": "نرخ فروش", "nonoperating_profit": "سود غیرعملیاتی",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize(value):
    return re.sub(r"\s+", " ", str(value).translate(str.maketrans(
        "يك۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "یک01234567890123456789"
    )).replace("\u200c", " ")).strip()


def source_url(value):
    parsed = urlparse(value)
    return (parsed.scheme == "https" and parsed.hostname in {"codal.ir", "www.codal.ir"}
            and not parsed.username and not parsed.password and parsed.port in {None, 443})


def period_date(value):
    """Validate explicit Jalali period labels without guessing a calendar conversion."""
    value = normalize(value).replace("-", "/")
    if not re.fullmatch(r"1[34]\d{2}/\d{2}/\d{2}", value):
        raise ValueError("Explicit Jalali fiscal period required")
    year, month, day = map(int, value.split("/"))
    if not 1 <= month <= 12 or not 1 <= day <= (31 if month <= 6 else 30):
        raise ValueError("Invalid fiscal period")
    return value


def number(value):
    if value is None or normalize(value) in {"", "-", "—", "N/A"}:
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a financial number")
    raw = normalize(value).replace(",", "").replace("٬", "").replace("٫", ".")
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    result = float(raw)
    if not math.isfinite(result):
        raise ValueError("Non-finite financial number")
    return result


def settings():
    defaults = {"years": 5, "sync_ttl_seconds": 21600, "smart_weight": .15,
                "weights": {"growth": 20, "profitability": 20, "cashFlow": 15,
                            "capitalStructure": 15, "earningsQuality": 15, "stability": 15}}
    path = os.getenv("SMART_FINANCIAL_CONFIG")
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        defaults.update({k: v for k, v in data.items() if k != "weights"})
        defaults["weights"].update(data.get("weights", {}))
    if (type(defaults["years"]) is not int or defaults["years"] < 5
            or not 0 <= defaults["smart_weight"] <= 1
            or not math.isfinite(defaults["sync_ttl_seconds"])
            or defaults["sync_ttl_seconds"] < 0
            or any(not math.isfinite(v) or v < 0 for v in defaults["weights"].values())
            or sum(defaults["weights"].values()) <= 0):
        raise ValueError("Invalid historical financial configuration")
    return defaults


class HistoricalDataRepository(SnapshotStore):
    """Extend existing SQLite store; market and financial datasets stay separate."""

    def __init__(self, path=None):
        super().__init__(path or os.getenv("SMART_HISTORICAL_DB"))
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS financial_documents (
                  symbol TEXT NOT NULL, document_id TEXT NOT NULL, digest TEXT NOT NULL,
                  source_url TEXT NOT NULL, source_date TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                  raw TEXT NOT NULL, report TEXT NOT NULL,
                  PRIMARY KEY(symbol,document_id,digest));
                CREATE TABLE IF NOT EXISTS financial_metrics (
                  symbol TEXT NOT NULL, document_id TEXT NOT NULL, digest TEXT NOT NULL,
                  period TEXT NOT NULL, report_type TEXT NOT NULL, basis TEXT NOT NULL,
                  metric TEXT NOT NULL, value REAL, unit TEXT NOT NULL, locator TEXT NOT NULL,
                  PRIMARY KEY(symbol,document_id,digest,period,report_type,basis,metric));
                CREATE TABLE IF NOT EXISTS historical_sync_log (
                  id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, source TEXT NOT NULL,
                  request_date TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS historical_sync_state (
                  symbol TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(symbol,source));
                CREATE TABLE IF NOT EXISTS historical_instruments (
                  symbol TEXT PRIMARY KEY, ins_code TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS codal_assets (
                  symbol TEXT NOT NULL, report_id TEXT NOT NULL, url TEXT NOT NULL,
                  digest TEXT NOT NULL, content_type TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                  payload BLOB NOT NULL, PRIMARY KEY(symbol,report_id,url,digest));
                CREATE TABLE IF NOT EXISTS codal_announcements (
                  symbol TEXT NOT NULL, report_id TEXT NOT NULL, metadata_hash TEXT NOT NULL,
                  payload TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                  PRIMARY KEY(symbol,report_id,metadata_hash));
                CREATE TABLE IF NOT EXISTS codal_monthly_reports (
                  symbol TEXT NOT NULL, report_id TEXT NOT NULL, digest TEXT NOT NULL,
                  period TEXT NOT NULL, publish_date TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                  raw TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(symbol,report_id,digest));
                CREATE TABLE IF NOT EXISTS product_sales (
                  symbol TEXT NOT NULL, report_id TEXT NOT NULL, digest TEXT NOT NULL,
                  period TEXT NOT NULL, product TEXT NOT NULL, market TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(symbol,report_id,digest,product,market));
                CREATE TABLE IF NOT EXISTS calculated_metrics (
                  symbol TEXT NOT NULL, dataset TEXT NOT NULL, fingerprint TEXT NOT NULL,
                  generated_at TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(symbol,dataset,fingerprint));
                CREATE VIEW IF NOT EXISTS market_history AS
                  SELECT symbol,market_date AS trading_date,source,observed_at,payload
                  FROM daily_history WHERE source='tsetmc';
            """)

    def register_instrument(self, symbol, ins_code):
        if not str(ins_code).isdigit():
            return
        with self._connect() as con:
            con.execute("INSERT INTO historical_instruments VALUES(?,?) ON CONFLICT(symbol) DO UPDATE SET ins_code=excluded.ins_code",
                        (normalize(symbol), str(ins_code)))

    def instrument_symbols(self, ins_code):
        with self._connect() as con:
            return [r[0] for r in con.execute("SELECT symbol FROM historical_instruments WHERE ins_code=?", (str(ins_code),))]

    def known_documents(self, symbol):
        with self._connect() as con:
            return {r[0] for r in con.execute(
                "SELECT document_id FROM financial_documents WHERE symbol=?", (normalize(symbol),))}

    def asset(self, symbol, report_id, url):
        with self._connect() as con:
            row = con.execute("SELECT payload,content_type,digest FROM codal_assets WHERE symbol=? AND report_id=? AND url=? ORDER BY retrieved_at DESC LIMIT 1",
                              (normalize(symbol), str(report_id), url)).fetchone()
        return {"payload": row[0], "content_type": row[1], "digest": row[2]} if row else None

    def save_monthly(self, report, raw):
        from .codal_operations import parse_monthly
        letter = {"Symbol": report["symbol"], "CompanyName": report.get("company"),
                  "Title": report["source_title"], "TracingNo": report["report_id"],
                  "PublishDateTime": report["publish_date"]}
        parsed = parse_monthly(letter, raw, report["symbol"], report["source_url"])
        if parsed != report:
            raise ValueError("Monthly report evidence mismatch")
        payload = json.dumps(report, ensure_ascii=False, allow_nan=False)
        key = (report["symbol"], report["report_id"], report["digest"])
        with self._connect() as con:
            if con.execute("SELECT 1 FROM codal_monthly_reports WHERE symbol=? AND report_id=? AND digest=?", key).fetchone():
                return "skipped"
            old = con.execute("SELECT 1 FROM codal_monthly_reports WHERE symbol=? AND period=?", (report["symbol"], report["period"])).fetchone()
            con.execute("INSERT INTO codal_monthly_reports VALUES(?,?,?,?,?,?,?,?)",
                        (*key, report["period"], report["publish_date"], now(), raw, payload))
            for item in report["products"]:
                con.execute("INSERT INTO product_sales VALUES(?,?,?,?,?,?,?)",
                            (*key, report["period"], item["product"], item["market"], json.dumps(item, ensure_ascii=False, allow_nan=False)))
        return "updated" if old else "inserted"

    def monthly_sales(self, symbol, selected=True):
        with self._connect() as con:
            rows = [dict(json.loads(p), retrieved_at=t) for p, t in con.execute(
                "SELECT payload,retrieved_at FROM codal_monthly_reports WHERE symbol=? ORDER BY publish_date,retrieved_at", (normalize(symbol),))]
        if not selected:
            return rows
        chosen = {}
        for row in rows:
            chosen[row["period"][:7]] = row
        return sorted(chosen.values(), key=lambda r: r["period"])

    def product_sales(self, symbol):
        return [dict(product, symbol=normalize(symbol), report_id=r["report_id"],
                     publish_date=r["publish_date"], digest=r["digest"])
                for r in self.monthly_sales(symbol) for product in r["products"]]

    def save_calculated_dataset(self, symbol, dataset, payload):
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        with self._connect() as con:
            con.execute("INSERT OR IGNORE INTO calculated_metrics VALUES(?,?,?,?,?)",
                        (normalize(symbol), dataset, fingerprint, now(), encoded))
        return fingerprint

    def save_asset(self, symbol, report_id, url, payload, content_type):
        if not source_url(url):
            raise ValueError("Untrusted raw asset source")
        digest = hashlib.sha256(payload).hexdigest()
        with self._connect() as con:
            con.execute("INSERT OR IGNORE INTO codal_assets VALUES(?,?,?,?,?,?,?)",
                        (normalize(symbol), str(report_id), url, digest, content_type, now(), payload))
        return digest

    def announcement_changed(self, symbol, letter):
        # Stable metadata, not retrieval timestamps, detects an updated report ID.
        payload = json.dumps(letter, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._connect() as con:
            old = con.execute("SELECT metadata_hash FROM codal_announcements WHERE symbol=? AND report_id=? ORDER BY retrieved_at DESC LIMIT 1",
                              (normalize(symbol), str(letter["TracingNo"]))).fetchone()
            con.execute("INSERT OR IGNORE INTO codal_announcements VALUES(?,?,?,?,?)",
                        (normalize(symbol), str(letter["TracingNo"]), digest, payload, now()))
        return old is not None and old[0] != digest

    def save_report(self, report, raw):
        """Internal provider boundary. No web/AI endpoint accepts numerical imports.

        Raw evidence and parser locators are mandatory; callers must use the Codal
        provider, not treat an arbitrary URL string as proof of authenticity.
        """
        symbol = normalize(report["symbol"])
        if report.get("source") != "KODAL" or not source_url(report["source_url"]):
            raise ValueError("Untrusted financial source")
        if not raw or not report.get("document_id"):
            raise ValueError("Missing source evidence")
        # Re-derive evidence at the storage boundary: a model cannot alter a
        # parsed number while retaining a plausible URL/document identifier.
        from .codal import parse_document
        extracted = parse_document({"Symbol": symbol, "Title": report.get("source_title", ""),
            "CompanyName": report.get("company"),
            "TracingNo": report["document_id"], "PublishDateTime": report["source_date"]},
            raw, symbol, report["source_url"])
        for field in ("period", "months", "report_type", "basis", "audited", "restated", "metrics"):
            if extracted[field] != report.get(field):
                raise ValueError(f"Financial evidence mismatch: {field}")
        period = period_date(report["period"])
        period_date(report["source_date"][:10])
        months = report["months"]
        kind = report["report_type"]
        if type(months) is not int or months not in {3, 6, 9, 12}:
            raise ValueError("Unsupported financial period length")
        if kind not in {"annual", "interim", "TTM"} or (kind == "annual") != (months == 12 and kind != "TTM"):
            raise ValueError("Report type/period mismatch")
        if report["basis"] not in {"standalone", "consolidated"}:
            raise ValueError("Unknown consolidation basis")
        if type(report["audited"]) is not bool or type(report["restated"]) is not bool:
            raise ValueError("Audit/restatement flags must be explicit")
        if not isinstance(report["metrics"], dict) or not report["metrics"]:
            raise ValueError("No recognized financial metrics")
        report = dict(report, symbol=symbol, period=period)
        values = {}
        for metric, item in report["metrics"].items():
            if metric not in METRICS or not item.get("locator") or not item.get("unit"):
                raise ValueError("Unknown metric or missing unit/source locator")
            values[metric] = number(item["value"])
        # Reject inconsistent totals, never repair them. Tolerance covers reporting rounding.
        if all(values.get(k) is not None for k in ("assets", "liabilities", "equity")):
            units = {report["metrics"][k]["unit"] for k in ("assets", "liabilities", "equity")}
            if len(units) != 1 or abs(values["assets"] - values["liabilities"] - values["equity"]) > max(2, abs(values["assets"]) * .001):
                raise ValueError("Balance sheet consistency failed")
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key = (symbol, str(report["document_id"]), digest)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM financial_documents WHERE symbol=? AND document_id=? AND digest=?", key).fetchone():
                return "skipped"
            previous = con.execute("SELECT 1 FROM financial_metrics WHERE symbol=? AND period=? AND basis=? AND report_type=?",
                                   (symbol, period, report["basis"], kind)).fetchone()
            con.execute("INSERT INTO financial_documents VALUES(?,?,?,?,?,?,?,?)",
                        (*key, report["source_url"], report["source_date"], now(), raw,
                         json.dumps(report, ensure_ascii=False, allow_nan=False)))
            for metric, value in values.items():
                item = report["metrics"][metric]
                con.execute("INSERT INTO financial_metrics VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (*key, period, kind, report["basis"], metric, value, item["unit"], item["locator"]))
        return "updated" if previous else "inserted"

    def reports(self, symbol, basis="standalone", selected=True):
        with self._connect() as con:
            rows = con.execute("SELECT report,digest,retrieved_at FROM financial_documents WHERE symbol=?",
                               (normalize(symbol),)).fetchall()
        reports = [dict(json.loads(r), digest=d, retrieved_at=t) for r, d, t in rows]
        reports = [r for r in reports if r["basis"] == basis]
        if not selected:
            return reports
        # Select whole reports, never fill holes from a superseded report. Audited
        # reports outrank unaudited; newer publication then restatement wins.
        chosen = {}
        for report in sorted(reports, key=lambda r: (r["audited"], r["source_date"], r["restated"], r["retrieved_at"])):
            chosen[(report["period"], report["report_type"])] = report
        return sorted(chosen.values(), key=lambda r: r["period"])

    def state(self, symbol, source):
        with self._connect() as con:
            row = con.execute("SELECT payload FROM historical_sync_state WHERE symbol=? AND source=?",
                              (normalize(symbol), source)).fetchone()
        return json.loads(row[0]) if row else {}

    def record_sync(self, symbol, source, result):
        result = dict(result, request_date=now())
        with self._connect() as con:
            con.execute("INSERT INTO historical_sync_log(symbol,source,request_date,payload) VALUES(?,?,?,?)",
                        (normalize(symbol), source, result["request_date"], json.dumps(result)))
            con.execute("INSERT INTO historical_sync_state VALUES(?,?,?) ON CONFLICT(symbol,source) DO UPDATE SET payload=excluded.payload",
                        (normalize(symbol), source, json.dumps(result)))
        return result

    def audit(self, symbol, limit=50):
        with self._connect() as con:
            return [json.loads(r[0]) for r in con.execute(
                "SELECT payload FROM historical_sync_log WHERE symbol=? ORDER BY id DESC LIMIT ?",
                (normalize(symbol), limit))]

    def fresh(self, symbol, source, ttl):
        state = self.state(symbol, source)
        return bool(state.get("request_date") and
                    (datetime.now(timezone.utc) - datetime.fromisoformat(state["request_date"])).total_seconds() < ttl)
