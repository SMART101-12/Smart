# SMART V2 — مسیر تکمیل از وضعیت فعلی تا اپلیکیشن کامل

## فاز 0 — تثبیت baseline

**وضعیت:** 🟡 در حال تثبیت

کارها:

- حفظ commit baseline `66445151`
- نگه داشتن branch پشتیبان
- جلوگیری از حذف کور داده
- تعیین ساختار نهایی runtime

## فاز 1 — سبز کردن validation pipeline

**اولویت: P0**

کارها:

1. اجرای `pytest -q tests/v2`
2. پیدا کردن failure دقیق آخرین CI
3. رفع علت واقعی failure
4. اجرای full test suite
5. اجرای PALAYESH validation
6. ثبت گزارش validation
7. سبز کردن GitHub Actions

**شرط خروج:** CI سبز + validation سبز.

## فاز 2 — تثبیت data architecture

**اولویت: P0**

تصمیم نهایی برای:

```text
raw
processed
monitored
analysis
validation
signals
outcomes
learning
```

ساختارهای legacy مانند `market_raw`، `market_processed`، `history` و سایر مسیرهای قدیمی نباید بدون بررسی حذف شوند؛ ابتدا باید مشخص شود کدام pipeline هنوز به آنها وابسته است.

## فاز 3 — Identity & schema

**اولویت: P0/P1**

ساخت canonical instrument registry:

```text
symbol
ins_code
isin
name
market
instrument_type
valid_from
source
```

هدف: جلوگیری از اشتباه نمادهای مشابه و امکان ردیابی تاریخی تغییرات instrument.

## فاز 4 — Raw/Processed/Monitored production pipeline

**اولویت: P1**

مسیر روزانه:

```text
TSETMC/MarketWatch
→ raw immutable
→ symbol snapshot
→ validation
→ normalized processed
→ monitored daily dataset
```

هر رکورد باید provenance داشته باشد.

## فاز 5 — Technical intelligence

**اولویت: P1**

پیاده‌سازی و تست گروه‌های شاخص:

- trend
- momentum
- volatility
- volume/value
- money flow
- smart-money proxy
- support/resistance
- market breadth

هر indicator باید unit test، definition و version داشته باشد.

## فاز 6 — Scoring / Ensemble

**اولویت: P1**

ساخت score چندعاملی با وزن‌های versioned.

نمونه مفهومی:

```text
Technical Score
+ Volume/Money Flow Score
+ Market Context Score
+ Fundamental Score
+ Data Quality Adjustment
= Final Score
```

وزن‌ها باید قابل تغییر و قابل backtest باشند.

## فاز 7 — Signal Engine

**اولویت: P1**

خروجی:

- Top candidates
- Top 3 actionable candidates
- entry zone
- stop/invalidation
- target
- risk/reward
- confidence
- reasons
- data quality

## فاز 8 — Outcome Engine

**اولویت: P1**

برای هر signal:

```text
T+1
T+3
T+5
```

با توجه به trading calendar و نوع instrument.

## فاز 9 — Learning Engine

**اولویت: P1/P2**

یادگیری باید از نتیجه واقعی سیگنال‌ها انجام شود، نه از خروجی‌های فرضی.

مسیر:

```text
signal
→ realized outcome
→ indicator attribution
→ weight evaluation
→ candidate weights
→ backtest
→ validation
→ promotion
```

## فاز 10 — Daily Automation

**اولویت: P1**

ساخت scheduler/orchestrator که:

1. calendar را چک کند.
2. داده روز را دریافت کند.
3. raw را ذخیره کند.
4. validation را اجرا کند.
5. processing را اجرا کند.
6. indicators را بسازد.
7. score را محاسبه کند.
8. signal تولید کند.
9. خروجی روزانه را ذخیره کند.
10. outcomeهای قبلی را update کند.
11. learning dataset را refresh کند.
12. گزارش روزانه تولید کند.

## فاز 11 — Dashboard / User Application

**اولویت: P2**

بعد از تثبیت engine:

```text
Dashboard
├── Market Overview
├── Top 10
├── Top 3
├── Portfolio
├── Signal History
├── Accuracy
├── Learning
├── Data Quality
└── Model Health
```

UI نباید قبل از تثبیت data/analysis engine مرجع حقیقت باشد.

## فاز 12 — Production hardening

**اولویت: P2**

- logging
- retry
- monitoring
- alerting
- backup
- schema migration
- reproducibility
- security/secrets
- Windows deployment
- Docker deployment
- disaster recovery

## ترتیب کل پروژه

```text
[CURRENT]
Architecture + Validation Foundation
        ↓
[P0] Fix failing tests
        ↓
[P0] Stable data architecture
        ↓
[P0/P1] Identity + canonical schema
        ↓
[P1] Raw → Processed → Monitored
        ↓
[P1] Indicators
        ↓
[P1] Score / Ensemble
        ↓
[P1] Signal Engine
        ↓
[P1] Outcome Engine
        ↓
[P1/P2] Learning Engine
        ↓
[P1] Daily Automation
        ↓
[P2] Dashboard / App
        ↓
[P2] Production Hardening
        ↓
SMART Production
```

## تعریف Done

SMART زمانی «کامل» محسوب می‌شود که:

- داده از منبع معتبر دریافت شود.
- raw قابل بازتولید باشد.
- identity معتبر باشد.
- quality gate سبز باشد.
- processed و monitored schema پایدار باشند.
- indicators محاسبه و تست شده باشند.
- score versioned باشد.
- signal با entry/exit/risk تولید شود.
- outcome واقعی ثبت شود.
- learning بدون look-ahead bias انجام شود.
- وزن‌ها با validation ارتقا پیدا کنند.
- اجرای روزانه خودکار باشد.
- dashboard از همان source of truth استفاده کند.
- کل pipeline end-to-end تست و CI سبز باشد.

تا قبل از این نقطه، SMART باید «در حال توسعه» تلقی شود، نه سیستم معاملاتی production-ready.
