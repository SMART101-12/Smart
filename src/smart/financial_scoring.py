"""Deterministic five-year analysis of repository evidence, never model numbers."""
from __future__ import annotations

from statistics import mean, pstdev
from math import isfinite

from .financial_history import METRICS, number, settings


RATIOS = {
    "gross_margin": ("gross_profit", "revenue", "حاشیه سود ناخالص"),
    "operating_margin": ("operating_profit", "revenue", "حاشیه سود عملیاتی"),
    "net_margin": ("net_profit", "revenue", "حاشیه سود خالص"),
    "roe": ("net_profit", "equity", "بازده حقوق صاحبان سهام (پایان دوره)"),
    "roa": ("net_profit", "assets", "بازده دارایی (پایان دوره)"),
    "cash_conversion": ("operating_cash_flow", "net_profit", "پوشش نقدی سود"),
    "debt_equity": ("liabilities", "equity", "بدهی به حقوق صاحبان سهام"),
    "finance_burden": ("finance_cost", "revenue", "بار هزینه مالی"),
    "nonoperating_share": ("nonoperating_profit", "net_profit", "سهم سود غیرعملیاتی"),
}
MISSING = "اطلاعات این شاخص برای دوره موردنظر در داده‌های دریافت‌شده از کدال موجود نیست."


def bounded(value):
    return max(0., min(100., value))


def growth(values):
    # Loss-to-profit and loss recovery are not conventional percentage growth.
    changes = [(b - a) / abs(a) for a, b in zip(values, values[1:]) if a != 0]
    if len(changes) != len(values) - 1:
        return None
    positive_fraction = sum(b > a for a, b in zip(values, values[1:])) / len(changes)
    return bounded(50 + 100 * mean(changes) + 20 * (positive_fraction - .5))


def stability(values):
    scale = mean(abs(v) for v in values)
    if scale == 0:
        return None
    # Stable losses do not earn a high stability grade.
    return bounded(100 * (1 - min(1, pstdev(values) / scale))) * sum(v > 0 for v in values) / len(values)


class FinancialScoringEngine:
    def __init__(self, repository, config=None):
        self.repository = repository
        self.config = config or settings()

    def analyze(self, symbol, basis="standalone"):
        repo, years = self.repository, self.config["years"]
        reports = [r for r in repo.reports(symbol, basis) if r["report_type"] == "annual" and r["months"] == 12]
        reports = reports[-years:]
        last_year = int(reports[-1]["period"][:4]) if reports else None
        slots = list(range(last_year - years + 1, last_year + 1)) if last_year else []
        by_year = {}
        for r in reports:
            by_year.setdefault(int(r["period"][:4]), []).append(r)
        # Changed year ends or multiple annual periods are not silently aligned.
        ends = {r["period"][5:] for r in reports}
        comparable = len(ends) == 1 and all(len(v) == 1 for v in by_year.values())
        series = {k: [] for k in [*METRICS, *RATIOS]}
        annual = []
        for year in slots:
            candidates = by_year.get(year, [])
            r = candidates[0] if len(candidates) == 1 else None
            cells = {}
            for metric in METRICS:
                item = r["metrics"].get(metric) if r else None
                value = number(item["value"]) if item else None
                cells[metric] = {"value": value, "unit": item["unit"] if item else None,
                    "badge": "KODAL VERIFIED" if value is not None else "N/A",
                    "source_reference": {"document_id": r["document_id"], "url": r["source_url"],
                        "digest": r["digest"], "locator": item["locator"], "source_date": r["source_date"]}
                        if item else None}
            for metric, (a, b, _) in RATIOS.items():
                av, bv = cells[a]["value"], cells[b]["value"]
                value = av / bv if (av is not None and bv is not None and bv > 0
                                     and cells[a]["unit"] == cells[b]["unit"]) else None
                if value is not None and not isfinite(value):
                    value = None
                cells[metric] = {"value": value, "unit": "ratio", "formula": f"{a}/{b}",
                    "badge": "CALCULATED FROM VERIFIED DATA" if value is not None else "N/A",
                    "source_reference": [cells[a]["source_reference"], cells[b]["source_reference"]]
                                    if value is not None else None}
            for metric, cell in cells.items():
                series[metric].append(cell["value"])
            annual.append({"year": year, "period": r["period"] if r else None, "cells": cells,
                           "audited": r["audited"] if r else None,
                           "restated": r["restated"] if r else None})

        def grade(metric, rule):
            values = series[metric]
            units = {row["cells"][metric]["unit"] for row in annual}
            if not comparable or len(values) < years or None in values or len(units) != 1:
                return None
            return rule(values)

        rules = {
            "growth": [(m, "mean signed growth and growth-year share", growth)
                       for m in ("revenue", "operating_profit", "net_profit", "eps")],
            "profitability": [(m, "positive margin/return level; negative values penalized",
                               lambda v: bounded(50 + 100 * mean(v)))
                              for m in ("gross_margin", "operating_margin", "net_margin", "roe", "roa")],
            "cashFlow": [("operating_cash_flow", "positive cash years and growth",
                          lambda v: mean([100 * sum(x > 0 for x in v) / len(v), growth(v)]) if growth(v) is not None else None),
                         ("cash_conversion", "cash covers profit; capped at full coverage",
                          lambda v: bounded(100 * mean(v)))],
            "capitalStructure": [("debt_equity", "lower leverage and declining trend preferred",
                                  lambda v: bounded(100 - 30 * mean(v) - 10 * (v[-1] - v[0]))),
                                 ("finance_burden", "lower absolute financing burden preferred",
                                  lambda v: bounded(100 - 200 * mean(abs(x) for x in v)))],
            "earningsQuality": [("cash_conversion", "cash-profit divergence penalized",
                                 lambda v: bounded(100 - 50 * mean(abs(1 - x) for x in v))),
                                ("nonoperating_share", "nonoperating dependence penalized",
                                 lambda v: bounded(100 - 100 * mean(abs(x) for x in v)))],
            "stability": [(m, "coefficient of variation with positive-year gate", stability)
                          for m in ("revenue", "net_profit", "net_margin")],
        }
        components = {}
        for category, items in rules.items():
            details = [{"metric": m, "rule": text, "score": grade(m, rule)} for m, text, rule in items]
            available = [d["score"] for d in details if d["score"] is not None]
            # No silent weight redistribution around unavailable inputs.
            score = mean(available) if len(available) == len(details) else None
            components[category] = {"score": score, "weight": self.config["weights"][category], "metrics": details}
        active = [c for c in components.values() if c["weight"] > 0]
        complete = bool(active) and all(c["score"] is not None for c in active)
        score = round(sum(c["score"] * c["weight"] for c in active) / sum(c["weight"] for c in active), 2) if complete else None
        count = sum(row["period"] is not None for row in annual)
        observed = sum(cell["value"] is not None for row in annual for m, cell in row["cells"].items() if m in METRICS)
        sync = repo.state(symbol, "KODAL")
        coverage = count / years
        completeness = observed / (years * len(METRICS))
        verification = 1 if reports else 0
        structural = 1 if comparable else 0
        fresh = 1 if repo.fresh(symbol, "KODAL", self.config["sync_ttl_seconds"]) and sync.get("status") == "SUCCESS" else 0
        quality = round(100 * (.3 * coverage + .35 * completeness + .15 * verification + .1 * structural + .1 * fresh), 2)
        result = {"symbol": symbol, "basis": basis, "financial_score": score,
            "status": "VERIFIED" if score is not None else "Insufficient verified data",
            "data_quality_score": quality, "data_quality_components": {"coverage": coverage,
                "completeness": completeness, "source_verification": verification,
                "structural_consistency": structural, "freshness": fresh},
            "coverage": {"available": count, "required": years}, "comparable": comparable,
            "source": "KODAL", "annual": annual, "components": components,
            "labels": {**METRICS, **{k: v[2] for k, v in RATIOS.items()}},
            "freshness": {"first_available_date": reports[0]["period"] if reports else None,
                "last_available_date": reports[-1]["period"] if reports else None,
                "last_sync_date": sync.get("last_sync_date"), "record_count": observed},
            "sync": sync, "warnings": [], "method_version": "historical-financial-v1"}
        if sync.get("status") in {"PARTIAL", "SOURCE_UNAVAILABLE"}:
            result["warnings"].append("داده جدید به‌طور کامل دریافت نشد. تحلیل بر اساس آخرین اطلاعات معتبر ذخیره‌شده انجام شده است."
                                      if reports else "دریافت از کدال کامل نشد و داده معتبر محلی برای تحلیل موجود نیست.")
        if not comparable and reports:
            result["warnings"].append("دوره‌های مالی به علت تغییر پایان سال یا دوره تکراری قابل مقایسه نیستند.")
        result["persian_analysis"] = PersianFinancialAnalysisGenerator.generate(result)
        return result


class PersianFinancialAnalysisGenerator:
    """Evidence templates: no LLM output is accepted into numerical analysis."""
    @staticmethod
    def generate(result):
        facts = []
        for metric in ("revenue", "net_profit", "operating_profit", "net_margin",
                       "operating_cash_flow", "debt_equity", "cash_conversion"):
            rows = result["annual"]
            values = [r["cells"][metric]["value"] for r in rows]
            if not result["comparable"] or len(values) < result["coverage"]["required"] or None in values:
                text = MISSING
            else:
                direction = "افزایش" if values[-1] > values[0] else "کاهش" if values[-1] < values[0] else "بدون تغییر"
                text = f"مقایسه نخستین و آخرین دوره موجود: {direction}. این مقایسه به معنی روند یکنواخت نیست."
            facts.append({"metric": metric, "title": result["labels"][metric], "text": text,
                          "references": [r["cells"][metric]["source_reference"] for r in rows
                                         if r["cells"][metric]["value"] is not None]})
        strengths = [name for name, c in result["components"].items() if c["score"] is not None and c["score"] >= 65]
        weaknesses = [name for name, c in result["components"].items() if c["score"] is not None and c["score"] <= 35]
        return {"facts": facts, "strengths": strengths, "weaknesses": weaknesses,
                "risks": result["warnings"], "score": result["financial_score"],
                "conclusion": "داده معتبر برای امتیازدهی کامل کافی نیست." if result["financial_score"] is None
                    else "امتیاز از داده‌های مستند و قواعد محاسباتی اعلام‌شده به دست آمده است."}


def integrate_financial_score(base_score, analysis):
    weight = settings()["smart_weight"]
    score = analysis["financial_score"]
    usable = score is not None and base_score is not None
    return {"score": round(base_score * (1 - weight) + score * weight, 2) if usable else base_score,
            "base_score": base_score, "financial_historical_score": score,
            "configured_weight": weight, "applied_weight": weight if usable else 0}
