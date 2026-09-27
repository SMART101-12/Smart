# SMART — گزارش کامل ممیزی، توسعه و مسیر ادامه

تاریخ این گزارش: **2026-08-29**
شاخهٔ کاری: `main`
مخزن: `SMART101-12/Smart`

## خلاصهٔ اجرایی

در این مرحله، اسکلت قابل‌تکرار زیر به پروژه اضافه و به تست وصل شد:

```text
منبع خام TSETMC / FRED
        ↓
دریافت و ثبت provenance
        ↓
آرشیو خامِ تغییرناپذیر
        ↓
نرمال‌سازی canonical + حذف تکراری‌های مشتق‌شده
        ↓
اعتبارسنجی تاریخ، قیمت، حجم و OHLC
        ↓
لایهٔ processed / monitored
        ↓
تحلیل تکنیکال + Smart Money + Multi-Factor + ریسک
        ↓
پیش‌بینی walk-forward و ثبت outcome
        ↓
آموزش محلیِ بدون look-ahead + حافظهٔ مثبت/منفی
```

دادهٔ خام برای قابلیت بازتولید حذف نمی‌شود. پاک‌سازی فایل فقط برای لایهٔ مشتق‌شده و با گزینهٔ صریح مجاز است.

## ممیزی شاخه‌ها

| مرجع | commit | وضعیت |
|---|---|---|
| `main` | `9b943903` | شاخهٔ فعلی |
| `origin/smart-v2-data-validation` | `65e5e16f` | acquisition/validation و تحلیل V2 |
| `origin/agent/data-gap-recovery` | `495593e1` | تاریخچهٔ all-market و gap recovery |
| `origin/docs/smart-v2-audit-20260825` | `c2a113eb` | roadmap و audit مستندات |
| `origin/smart-v2-gold-model` | `8391b390` | قرارداد دادهٔ یادگیری gold |
| `origin/smart-v2-ins-code-raw` | `e67c3409` | raw ingestion با InsCode |

هیچ branch، commit، push یا remote تغییری در این نوبت انجام نشده است.

## کارهای انجام‌شده

### ۱) دریافت و adapter

- `src/smart/tsetmc_adapter.py`
  - endpoint تک‌روز `closing_price_daily`
  - دریافت calendar نماد
  - `daily_history_incremental`
  - اتصال به `IncrementalHistorySync`
- `src/smart_v2/acquisition/fetchers.py`
  - اتصال واقعی MarketWatch TSETMC
  - پشتیبانی compact fields مثل `lva`, `pcl`, `qtj`
  - fallback آفلاین با برچسب روشن `synthetic_fixture`
- `src/smart_v2/acquisition/adapters.py`
  - نگاشت aliasها بدون از دست دادن ستون خام
  - تشخیص صفرهای placeholder در session بسته
- `src/smart_v2/processing/service.py`
  - استخراج همان aliasها از رکوردهای validated/legacy

### ۲) آرشیو، کیفیت و پاک‌سازی

- `src/smart/archive.py`
  - `normalize_daily_row`
  - `deduplicate_rows`
  - `validate_canonical_rows`
  - `archive_monthly`
  - `audit_archive_root`
  - `remove_exact_duplicate_derived_files`
- `src/smart/incremental.py`
  - بار اول: یک full-history request
  - دفعات بعد: فقط تاریخ‌های معاملاتی غایب
  - پنجشنبه/جمعه و تعطیلی صریح حذف از candidate dates
  - تاریخ‌های unresolved به‌عنوان صفر یا تعطیل جعل نمی‌شوند
  - آرشیو legacy و canonical هر دو به‌روزرسانی می‌شوند
- ابزار audit:
  - `scripts/audit_data_layers.py`

### ۳) بازار جهانی

- `src/smart/global_market.py`
- `scripts/sync_global_market.py`

provider پیش‌فرض، FRED CSV است و seriesهای زیر ثبت شده‌اند:

`DGS10`, `DFII10`, `DTWEXBGS`, `DEXUSEU`, `SP500`, `NASDAQCOM`, `VIXCLS`, `DCOILWTICO`, `NASDAQQGLDI`, `GVZCLS`

قواعد:

- فقط بازهٔ missing درخواست می‌شود.
- آخرین مقدار به‌صورت کور forward-fill نمی‌شود.
- تعطیلات/نبود observation در `unavailable_dates` ثبت می‌شود.
- هر observation دارای `source_id`, تاریخ observation و `retrieved_at` است.
- `NASDAQQGLDI` به‌عنوان proxy شاخص طلا نام‌گذاری شده و به‌اشتباه XAU/USD معرفی نمی‌شود.

### ۴) تحلیل سهم

- `src/smart_v2/analysis/stock_service.py`
  - ساخت DataFrame canonical
  - Smart Money
  - Multi-Factor
  - forecast قدیمیِ leakage-safe برای history
  - ATR و trade-plan پژوهشی
  - کیفیت و lineage
  - `analyze_and_save`
- `src/smart_v2/analysis/multi_factor_engine.py`
  - decision/risk level
  - قرارداد scalar به نام `calculate_composite_score`
- `src/smart_v2/analysis/gold_fund.py`
  - `evaluate_snapshot` و scalar mode برای قیمت/NAV

خروجی «BUY/SELL» تصمیم اجرایی کارگزاری نیست؛ فقط decision-support است.

### ۵) آموزش و یادگیری AI

- `src/smart_v2/ai/training.py`
  - feature snapshot فقط با history تا همان روز
  - target جداگانه برای horizon
  - train/validation/test زمانی
  - مدل dual-head ridge قابل‌ذخیره
  - baseline momentum/zero
  - معیارهای MAE و direction accuracy
  - تصمیم `PROMOTE` یا `REJECT`
  - ذخیرهٔ همهٔ آزمایش‌ها، حتی شکست‌خورده‌ها
  - ثبت outcome و error class
  - بارگذاری model artifact
- `src/smart_v2/ai/service.py`
  - APIهای `train` و `record_outcome` در کنار `predict`
- ابزار اجرا:
  - `scripts/train_smart_ai.py`

این بخش «fine-tuning مدل زبانی» نیست؛ یک مدل محلی عددی، قابل‌تست و بدون نشت داده برای تحلیل OHLCV است. اتصال توضیحی OpenAI در `src/smart/ai.py` جدا باقی مانده و به داده‌گیری دسترسی ندارد.

## مسیرهای مهم

```text
src/smart/tsetmc_adapter.py
src/smart/incremental.py
src/smart/archive.py
src/smart/global_market.py
src/smart_v2/acquisition/
src/smart_v2/processing/
src/smart_v2/analysis/stock_service.py
src/smart_v2/ai/training.py
runtime/market_raw/                  # evidence خام؛ حذف نشود
runtime/history/                     # آرشیو تاریخچهٔ فعلی
runtime/market_processed/canonical/  # آرشیو canonical جدید
runtime/data_quality/                # گزارش کیفیت و unresolvedها
runtime/global_market/               # آرشیو بازار جهانی
runtime/learning/                    # runها و outcomeهای AI
runtime/analysis/                    # خروجی تحلیل
```

## آمار دادهٔ موجود در workspace

- universe all-market ثبت‌شده: **3205** نماد
- تاریخچهٔ موفق در گزارش موجود: **2841**
- خطاهای ثبت‌شده برای همان run: **364**
- فایل‌های تاریخچهٔ raw موجود: **5686**
- رکوردهای raw شمارش‌شده: حدود **5,518,788**
- raw و history موجود در repository دست‌نخورده نگه داشته شد.

این آمار مربوط به artifactهای موجود workspace است، نه ادعای دریافت تازهٔ همهٔ سایت در این session.

## دستورات اجرایی

از ریشهٔ پروژه و با Python محیط Anaconda/virtualenv:

```powershell
$env:PYTHONPATH = ".\src"

# فقط audit، بدون حذف
python scripts/audit_data_layers.py --root runtime/market_processed/canonical

# حذف فقط فایل‌های byte-identical در derived root
python scripts/audit_data_layers.py `
  --root runtime/market_processed/canonical `
  --apply-derived-cleanup

# همگام‌سازی incremental نمادهای پیکربندی‌شده
python scripts/sync_tsetmc_incremental.py

# اجرای یک نماد/بازهٔ محدود برای بررسی
python scripts/sync_tsetmc_incremental.py `
  --symbol فولاد --start-date 2026-08-15 --end-date 2026-08-28

# بازار جهانی؛ فقط تاریخ‌های غایب
python scripts/sync_global_market.py --start-date 2026-01-01

# آموزش مدل روی تاریخچهٔ آرشیوشده
python scripts/train_smart_ai.py فولاد
```

برای دریافت all-market اولیه/ادامهٔ run قدیمی:

```powershell
python scripts/fetch_tsetmc_history_all.py
python scripts/fetch_tsetmc_history_all.py --retry-errors
```

progress در `runtime/market_raw/history_universe/<date>-all-market.json` نگه داشته می‌شود؛ run قطع‌شده از موفقیت‌های قبلی ادامه می‌دهد.

## تست و اعتبارسنجی

آخرین اجرای کامل:

```text
62 passed in 52.15s
```

تست‌های جدید:

- `tests/test_archive.py`
- `tests/test_incremental_sync.py`
- `tests/test_global_market.py`
- `tests/v2/test_training_and_stock_service.py`

همهٔ تست‌های قبلی نیز دوباره اجرا شدند. `py_compile` برای فایل‌های جدید موفق است؛ یک `SyntaxWarning` قدیمی در `scripts/data_entry_basic_metals.py` باقی است و خطای runtime نیست.

## محدودیت‌ها و مرحلهٔ بعد

1. اجرای full all-market تازه به‌علت حجم/زمان و محدودیت شبکه در این نوبت انجام نشد؛ ابزار resumable آماده است.
2. برای XAU/USD spot باید provider اختصاصیِ تأییدشده و مجوز/پایداری آن جداگانه اضافه شود؛ شاخص gold فعلی عمداً proxy نام‌گذاری شده است.
3. دادهٔ تاریخی order-book، حقیقی/حقوقی و sentiment در ورودی موجود نیست؛ از جعل آن‌ها خودداری شده است.
4. مدل فقط پس از چند پنجرهٔ OOS مستقل و مقایسه با baseline باید promote شود.
5. قبل از استفادهٔ عملی، transaction cost، slippage، execution و calendar نمادمحور باید به benchmark اضافه شود.
6. هیچ خروجی این repository تضمین سود یا توصیهٔ قطعی سرمایه‌گذاری نیست.

## قرارداد ادامهٔ توسعه

```text
Observe → Predict → Record → Reveal actual
        → Diagnose error → Learn → Next day
```

هر تغییر بعدی باید:

1. branch/status و artifactهای قبلی را بخواند؛
2. raw را immutable نگه دارد؛
3. یک تست مستقل اضافه کند؛
4. baseline و OOS را گزارش کند؛
5. نتیجهٔ شکست را حذف نکند؛
6. مسیر فایل و lineage را در artifact ثبت کند.
