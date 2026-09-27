"""Parse observed Codal monthly product grids, preserving reported units."""
import hashlib
import re

from .codal import Tables, embedded_tables, issuer_report, metric_label
from .financial_history import normalize, number, period_date, source_url


def operational_cell(raw_value, unit, locator, url, report_id, digest, published):
    value = number(raw_value)
    factors = {"million_IRR": (1000000, "IRR"), "billion_IRR": (1000000000, "IRR"),
               "هزار تن": (1000, "تن"), "هزارتن": (1000, "تن")}
    factor, normalized_unit = factors.get(unit, (1, unit))
    return {"raw_value": value, "raw_text": raw_value, "raw_unit": unit,
            "value": value * factor if value is not None else None, "unit": normalized_unit,
            "normalization_factor": factor, "source_type": "DIRECT" if value is not None else None,
            "source": "KODAL", "source_records": [{"report_id": str(report_id), "content_hash": digest,
                "source_url": url, "locator": locator, "published_at": published}]}


def parse_monthly(letter, raw, symbol, url):
    if not source_url(url) or not issuer_report(letter, symbol):
        raise ValueError("Monthly issuer/source mismatch")
    title = normalize(letter.get("Title", ""))
    end = re.search(r"منتهی به\s*(1[34]\d{2}/\d{2}/\d{2})", title)
    if not end or not re.search(r"دوره\s*1\s*ماهه", title) or "فعالیت ماهانه" not in title:
        raise ValueError("Explicit one-month activity disclosure required")
    period = period_date(end[1])
    published = normalize(letter["PublishDateTime"])
    period_date(published[:10])
    parser = Tables()
    parser.feed(raw)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    products, totals = [], {}
    for ti, table in enumerate(parser.tables + embedded_tables(raw)):
        if len(table) < 3:
            continue
        header, sub = table[:2]
        if not any("نام محصول" in h for h in sub):
            continue
        starts = [i for i, h in enumerate(header) if period in h and
                  ("یک ماهه" in h or "1 ماهه" in h) and "ابتدای" not in h]
        if len(starts) != 1:
            continue
        start = starts[0]
        stop = next((i for i in range(start + 1, len(header)) if header[i]), len(header))
        indexes = {}
        for ci in range(start, min(stop, len(sub))):
            label = metric_label(sub[ci])
            key = ("sales_value" if "مبلغ فروش" in label else "sales_quantity" if "فروش" in label and ("تعداد" in label or "مقدار" in label)
                   else "production_quantity" if "تولید" in label else "selling_price" if "نرخ فروش" in label else None)
            if key:
                if key in indexes:
                    raise ValueError("Ambiguous monthly column")
                indexes[key] = ci
        if "sales_value" not in indexes:
            continue
        sales_header = sub[indexes["sales_value"]]
        money_unit = "million_IRR" if "میلیون ریال" in sales_header else "billion_IRR" if "میلیارد ریال" in sales_header else "IRR" if "ریال" in sales_header else None
        if not money_unit:
            raise ValueError("Unknown monthly sales unit")
        market = None
        for ri, row in enumerate(table[2:], start=2):
            if not row or not row[0]:
                continue
            label = metric_label(row[0]).rstrip(":")
            section = {"فروش داخلی": "domestic", "فروش صادراتی": "export",
                       "درآمد ارائه خدمات": "services", "برگشت از فروش": "returns"}.get(label)
            if section:
                market = section
                continue
            cells = {}
            for metric, ci in indexes.items():
                unit = money_unit if metric == "sales_value" else "IRR/" + normalize(row[1]) if metric == "selling_price" else normalize(row[1])
                value = row[ci] if ci < len(row) and unit else None
                cells[metric] = operational_cell(value, unit or None, f"table:{ti}/row:{ri}/column:{ci}",
                    url, letter["TracingNo"], digest, published)
            if label in {"جمع", "جمع کل"}:
                if "total" in totals and totals["total"]["value"] != cells["sales_value"]["value"]:
                    raise ValueError("Conflicting monthly totals")
                totals["total"] = cells["sales_value"]
            elif label.startswith("جمع "):
                totals[label] = cells["sales_value"]
            elif label == "تخفیفات":
                totals[label] = cells["sales_value"]
            elif market:
                if not row[1]:
                    raise ValueError("Product row lacks unit")
                products.append({"product": label, "market": market, "period": period,
                                 "metrics": cells})
    if not products and "total" not in totals:
        raise ValueError("Unsupported monthly product grid")
    keys = [(r["product"], r["market"]) for r in products]
    if len(keys) != len(set(keys)):
        raise ValueError("Ambiguous duplicate product/market rows")
    total = totals.get("total") or operational_cell(None, "IRR", "unavailable", url, letter["TracingNo"], digest, published)
    return {"symbol": normalize(symbol), "company": letter.get("CompanyName"),
            "report_id": str(letter["TracingNo"]), "source": "KODAL", "source_url": url,
            "source_title": title, "period": period, "basis": "standalone",
            "publish_date": published, "restated": "اصلاح" in title,
            "digest": digest, "sales_value": total, "totals": totals, "products": products}
