"""Read-only explanations of recorded gates; never recompute a trading decision."""
from __future__ import annotations

from typing import Any


def explain_gates(summary: dict[str, Any]) -> list[dict[str, Any]]:
    gate = summary.get("quality_gate") or {}
    decision = summary.get("decision") or {}
    flow = summary.get("flow") or {}
    setup = summary.get("setup") or {}
    fund = summary.get("fundamental") or {}
    financial = summary.get("fundamental_quality_gate") or {}
    current = (gate.get("current_window") or {}).get("status", gate.get("status"))
    if decision.get("version") == "DECISION-1.1":
        current = gate.get("status")
    specifications = {
        "entry_validity": ("اعتبار زمانی ورود", "DATA", {"as_of": setup.get("as_of"),
                            "expires_on": setup.get("expires_on"), "state": setup.get("state")},
                           "تاریخ ارزیابی داخل مهلت ورود باشد و قیمت از محدوده ورود عبور نکرده باشد.",
                           "برای فرصت منقضی‌شده، تحلیل جدید لازم است؛ قیمت را تعقیب نکنید."),
        "net_reward_risk": ("بازده به ریسک پس از هزینه", "DATA", setup.get("net_reward_risk_1"),
                            "نسبت خالص باید به حداقل سیاست ثبت‌شده تحلیل برسد.",
                            "هزینه، لغزش، حد ضرر و مقاومت پیش رو بررسی شوند؛ هدف صرفاً برای قبولی بزرگ نشود."),
        "data_quality": ("کیفیت داده", "DATA", {"status": current, "latest": gate.get("latest_valid_date"),
                          "freshness": gate.get("freshness"), "blockers": gate.get("blockers")},
                         "پنجره مورد استفاده سالم، کندل آخر معتبر و داده تازه باشد.",
                         "ردیف‌های خراب همان پنجره و تازگی منبع بررسی شود؛ خطاهای قدیمی در حسابرسی باقی می‌مانند."),
        "adjustment_history": ("سابقه تعدیل قیمت", "DATA", gate.get("corporate_action_adjustment"),
                               "اقدامات شرکتی و مبنای تعدیل قیمت مستقل تأیید شود.",
                               "تاریخچه رسمی افزایش سرمایه و تقسیم سود به قیمت‌های همان دوره متصل شود."),
        "market_context": ("وضعیت بازار", "DATA", (summary.get("market") or {}).get("regime"),
                           "بازار با داده معتبر در وضعیت نزولی یا ریسک شدید نباشد.",
                           "تاریخ و منشأ شاخص کل و هم‌وزن بررسی شود."),
        "industry_context": ("وضعیت صنعت", "DATA", (summary.get("industry") or {}).get("regime"),
                             "صنعت یا ترکیب دارایی صندوق با داده تاریخ‌دار مشخص و مساعد باشد.",
                             "شناسه رسمی شاخص صنعت و عضویت نماد؛ برای صندوق ترکیب دارایی همان تاریخ تکمیل شود."),
        "context_source_verification": ("منبع شاخص‌ها", "DATA", {
            name: (summary.get(name) or {}).get("source_validation") for name in ("market", "industry")},
            "منبع هر دو لایه بازار و صنعت تأیید شود.", "شناسه، نام شاخص و تاریخ داده با پاسخ رسمی تطبیق داده شود."),
        "technical_alignment": ("هم‌جهتی تکنیکال", "SIGNAL", (summary.get("technical_structure") or {}).get("score_0_100"),
                                "امتیاز توصیفی تکنیکال حداقل ۶۰ از ۱۰۰ باشد.", "ساختار روزانه، هفتگی و ماهانه و تعارض روندها بررسی شود."),
        "setup_confirmation": ("تأیید الگوی ورود", "SIGNAL", setup.get("state"),
                               "الگو تأیید شده و برنامه ورود معتبر داشته باشد.",
                               "تأیید شکست/بازآزمایی، حجم و سایر شروط الگو در جلسه کامل بعدی بررسی شود."),
        "validation": ("اعتبارسنجی مدل", "MODEL", (summary.get("self_test") or {}).get("decision"),
                       "اعتبارسنجی و آزمون نهایی جداگانه قبول شوند.",
                       "نمونه، عملکرد خارج از آموزش و هزینه بررسی شود؛ صعودی بودن اندیکاتورها رد مدل را جبران نمی‌کند."),
        "approved_model_version": ("نسخه تأییدشده مدل", "POLICY", (summary.get("model_policy") or {}).get("state"),
                                   "نسخه معتبر مدل به‌صورت مستقل بررسی و تأیید شده باشد.",
                                   "مسیر تأیید نسخه پس از اعتبارسنجی تکمیل شود؛ مدل پژوهشی خودکار فعال نمی‌شود."),
        "individual_flow": ("جریان پول حقیقی", "DATA", (flow.get("observed_client_type") or {}).get("signal"),
                            "ورود حقیقی با ClientType تاریخ‌دار تأیید شود و تعارض نداشته باشد.",
                            "داده حقیقی همان جلسه دریافت شود؛ تغییر حجم قیمت جایگزین این منبع نیست."),
        "volume_confirmation": ("تأیید حجم", "SIGNAL", {
            "percent_of_20_session_mean": (flow.get("price_volume_proxy") or {}).get("volume_ratio_20") * 100
            if isinstance((flow.get("price_volume_proxy") or {}).get("volume_ratio_20"), (int, float)) else None},
            "حجم حداقل ۱۲۰٪ میانگین ۲۰ جلسه باشد.", "حجم واقعی جلسه کامل با میانگین جلسات قبلی مقایسه شود."),
        "financial_publication": ("انتشار کدال", "DATA", financial.get("source_status"),
                                  "سند قبل از تاریخ تحلیل منتشر و گیت انتشار بدون مانع باشد.",
                                  "دریافت، خواندن قالب، تاریخ انتشار و اصلاحیه‌ها جداگانه بررسی شود."),
        "fundamental_completeness": ("کفایت بنیادی", "DATA", fund.get("valuation_score")
                                     if summary.get("instrument_type") == "FUND" else fund.get("financial_score"),
                                     "بنیادی قابل محاسبه باشد؛ صندوق NAV معتبر و قیمت هم‌جلسه نیاز دارد.",
                                     "صورت‌های مالی و واحدها تکمیل شوند؛ NAV صفر/قدیمی یا مقدار مفقود امتیاز نمی‌سازد."),
        "risk_constraints": ("ریسک اجرا", "DATA", {k: setup.get(k) for k in
                              ("risk", "reward_risk_1", "liquidity", "gap_execution_risk")},
                             "ریسک کم/متوسط، سود به زیان حداقل ۲ و نقدشوندگی و ریسک گپ تأیید شود.",
                             "حجم/ارزش معامله، هزینه و شرایط اجرای گپ با داده مستقل سنجیده شود."),
        "complete_evidence": ("پوشش شواهد", "DATA", decision.get("evidence_coverage_weight_pct"),
                              "تمام دسته‌های دارای وزن، شواهد معتبر داشته باشند.",
                              "دسته‌های مفقود تکمیل شوند؛ وزن آن‌ها روی دسته‌های دیگر پخش نمی‌شود."),
    }
    return [{"key": key, "title": spec[0], "category": spec[1], "observed": spec[2],
             "required": spec[3], "next_step": spec[4], "passed": passed}
            for key, passed in decision.get("gates", {}).items()
            if (spec := specifications.get(key)) is not None]


def report_source_health(summary: dict) -> list[dict]:
    gate = summary.get("quality_gate") or {}
    codal = summary.get("fundamental_quality_gate") or {}
    fundamental = summary.get("fundamental") or {}
    observed = (summary.get("flow") or {}).get("observed_client_type") or {}
    return [
        {"source": "TSETMC", "status": gate.get("status", "UNAVAILABLE"),
         "data_date": gate.get("latest_valid_date"), "freshness": gate.get("freshness"),
         "acquisition": gate.get("acquisition"),
         "conflicting_dates": gate.get("conflicting_duplicate_dates", []),
         "price_range_validation": gate.get("price_range_validation"),
         "errors": gate.get("blockers", []), "description": "قیمت و حجم؛ سلامت کل تاریخچه و پنجره اخیر جدا هستند."},
        {"source": "کدال", "status": codal.get("source_status", "UNAVAILABLE"),
         "data_date": codal.get("latest_publication_date"), "errors": codal.get("blockers", []),
         "description": "موفقیت دریافت، به معنی کفایت مالی یا NAV جاری نیست."},
        {"source": "NAV صندوق", "status": "AVAILABLE" if fundamental.get("valuation_score") is not None else "UNAVAILABLE",
         "data_date": (fundamental.get("net_asset_value_per_unit") or {}).get("as_of"),
         "errors": fundamental.get("missing_data", []), "description": "ارزش‌گذاری فقط با NAV معتبر و قیمت هم‌جلسه."}
        if summary.get("instrument_type") == "FUND" else
        {"source": "بنیادی شرکت", "status": "AVAILABLE" if fundamental.get("financial_score") is not None else "UNAVAILABLE",
         "data_date": codal.get("latest_period"), "errors": [], "description": "کفایت صورت‌های مالی و واحدهای استخراج‌شده."},
        *[{"source": "شاخص بازار" if name == "market" else "شاخص صنعت / ترکیب صندوق",
           "status": (summary.get(name) or {}).get("status", "UNAVAILABLE"),
           "data_date": (summary.get(name) or {}).get("as_of"),
           "errors": (summary.get(name) or {}).get("conflicts", []),
           "description": "منبع: " + str((summary.get(name) or {}).get("source") or "ناموجود")}
          for name in ("market", "industry")],
        {"source": "جریان حقیقی", "status": observed.get("status", "UNAVAILABLE"),
         "data_date": observed.get("as_of"), "errors": (summary.get("flow") or {}).get("conflicts", []),
         "description": "داده حقیقی تاریخ‌دار، مستقل از نشانه‌های حجمی."},
    ]
