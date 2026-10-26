"""Render conclusions from immutable computed facts, never model-authored claims."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def explanation_facts(reference: dict[str, Any]) -> dict[str, str]:
    """Server-authored sentences. Model output may reference IDs only."""
    def shown(value):
        return "نامشخص" if value is None else str(value)

    gate = reference.get("quality_gate") or {}
    quality = reference.get("data_quality") or {}
    final = reference.get("final_assessment") or {}
    decision = reference.get("decision") or {}
    facts = {
        "identity": f"تحلیل {reference.get('symbol', '')} بر اساس داده تا تاریخ {shown(reference.get('as_of'))} است.",
        "quality": f"وضعیت کیفیت داده: {shown(gate.get('status') or quality.get('status'))}. مشکلات داده: "
                   + ("، ".join(gate.get("blockers") or quality.get("issues") or []) or "مشکلی در کنترل‌های انجام‌شده ثبت نشده است؛ این به معنی تأیید کامل منبع نیست."),
        "decision": "جمع‌بندی موتور محاسباتی: " + shown(decision.get("state") or final.get("label")) + ".",
        "confidence": "احتمال موفقیت پیش‌بینی کالیبره نشده است؛ امتیاز کیفیت داده و امتیاز شواهد، احتمال سود نیستند.",
    }
    momentum = reference.get("momentum") or {}
    if momentum:
        facts["momentum"] = "RSI: " + shown(momentum.get("rsi")) + "؛ MACD: " + shown(momentum.get("macd")) + "."
    technical = reference.get("technical_structure") or reference.get("technical") or {}
    for name, frame in (technical.get("timeframes") or {}).items():
        title = {"daily": "روزانه", "weekly": "هفتگی", "monthly": "ماهانه"}.get(name, name)
        trend = {"UP": "صعودی", "DOWN": "نزولی", "MIXED": "مختلط"}.get(frame.get("trend"), "نامشخص")
        facts["timeframe_" + name] = f"افق {title}: وضعیت {shown(frame.get('status'))}؛ {shown(frame.get('bars'))} مشاهده تا {shown(frame.get('last_completed'))}؛ آخرین قیمت {shown(frame.get('last_close'))} و روند محاسبه‌شده {trend}."
        if frame.get("status") == "SUCCESS":
            facts["timeframe_" + name] += (f" کف و سقف بازهٔ اخیر: {shown(frame.get('support'))} و {shown(frame.get('resistance'))}؛ "
                f"وضعیت شکست بازه: {shown(frame.get('breakout'))}. این بازه به‌تنهایی نقطهٔ ورود یا هدف معامله نیست.")
    for name, title in (("market", "بازار"), ("industry", "صنعت")):
        layer = reference.get(name) or {}
        if layer:
            facts[name] = f"وضعیت {title}: {shown(layer.get('status'))}؛ رژیم محاسبه‌شده {shown(layer.get('regime'))}."
    fundamental = reference.get("fundamental") or {}
    if fundamental:
        facts["fundamental"] = "امتیاز بنیادی مشاهده‌شده در گزارش: " + shown(fundamental.get("financial_score")) + "؛ اعتبار این نتیجه به پوشش اسناد و کنترل کیفیت انتشار کدال وابسته است."
    flow = reference.get("flow") or {}
    if flow:
        facts["flow"] = ("جریان پول: وضعیت " + shown(flow.get("status"))
            + "؛ نتیجه دادهٔ حقیقی و حقوقی " + shown((flow.get("observed_client_type") or {}).get("signal"))
            + "؛ نتیجهٔ الگوی قیمت و حجم " + shown((flow.get("price_volume_proxy") or {}).get("signal"))
            + ". الگوی قیمت و حجم به‌تنهایی تأیید ورود پول حقیقی نیست.")
    failed_gates = decision.get("failed_gates") or []
    if failed_gates:
        facts["decision_gates"] = "جمع‌بندی به این شروط تأییدنشده وابسته است: " + "، ".join(failed_gates) + "."
    for name, horizon in (reference.get("horizon_summaries") or {}).items():
        facts["horizon_" + name] = f"بازه {name} جلسه: {horizon['observations']} مشاهده از {shown(horizon['from_date'])} تا {shown(horizon['to_date'])}؛ کف {shown(horizon['low'])}، سقف {shown(horizon['high'])}؛ کفایت داده: {horizon['status']}."
    levels = reference.get("entry_exit") or {}
    plan = levels.get("plan") or levels.get("conditional")
    evidence = levels.get("level_evidence") or (plan or {}).get("level_evidence") or {}
    verified = (levels.get("engine_version") == "STRUCTURAL-ENTRY-1" and plan
                and plan.get("target_method") == "observed_pivot_resistance"
                and evidence.get("target_1") and evidence.get("target_2"))
    if verified:
        facts["entry_exit"] = ("سناریوی ورود و خروج مشروط به تأیید شروط گزارش است: محدوده ورود "
            + shown(plan.get("entry_zone_if_confirmed", plan.get("entry_zone")))
            + "؛ حد ضرر " + shown(plan.get("stop_if_entered", plan.get("sl")))
            + "؛ هدف اول " + shown(plan.get("target_1_if_entered", plan.get("tp1")))
            + "؛ هدف دوم " + shown(plan.get("target_2_if_entered", plan.get("tp2"))) + ".")
    else:
        facts["entry_exit"] = "نقاط ورود و خروج تأییدشده در دسترس نیست؛ عدد جایگزین تولید نمی‌شود."
    missing = reference.get("missing_data") or []
    if missing:
        facts["missing"] = "داده یا شواهد ناقص: " + "، ".join(missing) + "."
    facts["limitations"] = "این تحلیل بر مشاهدات موجود متکی است؛ اعتبار بازه قیمتی، تأیید تعدیل قیمت و کیفیت منبع باید همراه نتیجه خوانده شود."
    return facts


def render_explanation(reference: dict, selected_ids: list[str] | None = None) -> dict:
    facts = explanation_facts(reference)
    order = list(facts)
    if selected_ids is not None:
        if (not isinstance(selected_ids, list) or not selected_ids
                or any(not isinstance(key, str) or key not in facts for key in selected_ids)
                or len(set(selected_ids)) != len(selected_ids)):
            raise RuntimeError("Explanation contains an unknown or duplicate fact reference")
        # Include every caveat and conclusion, even if the model omits them.
        order = selected_ids + [key for key in facts if key not in selected_ids]
    return {"answer": "\n\n".join(facts[key] for key in order), "fact_ids": order,
            "reference_sha256": fingerprint(reference), "method": "computed_fact_rendering"}
