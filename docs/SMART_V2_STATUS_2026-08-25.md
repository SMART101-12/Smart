# SMART V2 — وضعیت فنی و میزان تکمیل

**تاریخ ممیزی:** 2026-08-25  
**Branch مبنا:** `smart-v2-data-validation`  
**Commit مبنا:** `664451518cc940efcb084d6fdcebe1b7c08ef5fa`  
**وضعیت Git محلی طبق گزارش کاربر:** CLEAN و همگام با `origin/smart-v2-data-validation`

## 1. نتیجه اجرایی

SMART V2 در وضعیت **اسکلت معماری + زیرساخت اعتبارسنجی تاریخی + ingestion اولیه** قرار دارد؛ هنوز یک موتور کامل تحلیل و تصمیم‌گیری معاملاتی نیست.

بخش‌هایی که واقعاً ساخته شده‌اند:

- جداسازی معماری V2 به acquisition / processing / validation / analysis / AI
- قراردادها و مدل‌های پایه در `src/smart_v2/core`
- لایه acquisition برای اتصال به TSETMC موجود
- splitter برای MarketWatch
- پردازش اولیه رکوردهای بازار
- تحلیل اولیه بازده روزانه
- validation و history-quality
- تست‌های واحد V2
- workflow خودکار GitHub Actions برای تست و validation
- مستندات و پروتکل‌های آموزشی AI

بخش‌هایی که هنوز کامل نیستند:

- pipeline یکپارچه end-to-end از دریافت تا signal
- identity enrichment با `InsCode`/ISIN
- normalized canonical dataset کامل
- market monitored layer عملیاتی
- مجموعه شاخص‌های تکنیکال/حجم/پول هوشمند
- scoring و وزن‌دهی نسخه‌بندی‌شده
- signal engine و entry/exit/risk logic
- outcome tracking در افق 1/3/5 روز
- learning loop واقعی برای اصلاح وزن‌ها
- سرویس اجرایی روزانه و orchestration کامل
- تست integration/end-to-end و تست داده واقعی در همه لایه‌ها
- پاکسازی و تثبیت نهایی ساختار قدیمی runtime

## 2. وضعیت هر لایه

| لایه | وضعیت | ارزیابی |
|---|---|---|
| Core contracts/models | 🟢 پایه ساخته شده | قراردادهای پایه وجود دارد، ولی هنوز باید کامل‌تر و سخت‌گیرانه‌تر شود |
| Acquisition | 🟢/🟡 | اتصال به adapter موجود و MarketWatch splitter وجود دارد؛ production pipeline کامل نیست |
| Raw data | 🟡 | ساختارهای قدیمی و جدید هم‌زمان در repo دیده می‌شوند و نیازمند معماری نهایی هستند |
| Validation | 🟢/🟡 | history quality و validators وجود دارند و بخش مهمی تست شده؛ پوشش جامع هنوز لازم است |
| Processing | 🟡 | استخراج چند فیلد مشتق‌شده انجام می‌شود؛ normalization کامل نیست |
| Analysis | 🟡 | daily return پیاده شده؛ تحلیل تکنیکال/فاندامنتال واقعی هنوز وارد V2 نشده است |
| AI | 🔴/🟡 | boundary سرویس وجود دارد اما موتور مدل/feature pipeline/learning کامل نیست |
| Signals | 🔴 | موتور سیگنال مستقل و production-ready وجود ندارد |
| Learning | 🔴 | پروتکل‌ها و مستندات وجود دارند، اما حلقه یادگیری عملیاتی کامل نیست |
| Daily automation | 🟡 | workflowهای GitHub وجود دارند، ولی اجرای روزانه کامل محصول هنوز ساخته نشده |
| Deployment | 🟡 | Docker/installer/workflow وجود دارد، اما acceptance end-to-end لازم است |

## 3. شواهد فنی

### Core

`src/smart_v2/core/contracts.py` و `models.py` قرارداد و مدل پایه را فراهم می‌کنند.

### Acquisition

`AcquisitionService` فقط adapter موجود TSETMC را expose می‌کند و عمداً نباید processing انجام دهد. `marketwatch_splitter.py` نیز برای شکستن MarketWatch وجود دارد.

### Processing

`ProcessingService` در حال حاضر از رکورد خام چند مقدار مانند close، last price، price change، volume، trade count و trade value را استخراج می‌کند. این هنوز normalization کامل نیست.

### Analysis

`AnalysisService` در وضعیت فعلی یک محاسبه مشخص، یعنی `daily_return`، را انجام می‌دهد. این به معنی تکمیل موتور تحلیل SMART نیست.

### AI

`AIService` صرفاً `model.predict(features)` را صدا می‌زند. بنابراین لایه AI فعلاً یک boundary است، نه سیستم یادگیری کامل.

### Validation

`history_quality.py` تقویم پایه و overrideهای V2 را در تعیین روزهای بسته استفاده می‌کند و gap detection و zero-trade classification دارد.

## 4. وضعیت تست فعلی

آخرین GitHub Actions مربوط به همین commit (`66445151`) در workflow `SMART V2 Validation` اجرا شده است.

نتیجه:

**FAIL** — بنابراین این commit را نباید baseline سبز یا production-ready تلقی کرد.

مراحل CI:

- checkout: PASS
- setup Python 3.12: PASS
- install dependencies: PASS
- V2 unit tests: **FAIL**
- PALAYESH validation: SKIPPED به دلیل شکست تست
- promotion: SKIPPED
- commit validated dataset: SKIPPED

Workflow تست V2 دستور `python -m pytest -q tests/v2` را با `PYTHONPATH=./src` اجرا می‌کند.

> نکته: از طریق API موجود، متن کامل log شکست تست در این ممیزی قابل بازیابی نبود؛ بنابراین علت دقیق failure را حدس نمی‌زنیم. اولین کار فنی بعدی باید اجرای همان command در محیط محلی و ثبت خروجی کامل باشد.

## 5. نتیجه نهایی

**SMART V2 از نظر معماری پایه قابل ادامه است، اما از نظر محصول تحلیلی/معاملاتی کامل نشده است.**

در حال حاضر بیشترین ریسک پروژه در سه نقطه است:

1. شکست تست V2 که باید قبل از توسعه بعدی رفع شود.
2. هم‌زیستی ساختارهای قدیمی و جدید runtime که باید با یک data contract نهایی تعیین تکلیف شود.
3. فاصله زیاد بین analysis/AI boundary فعلی و موتور واقعی indicator → score → signal → outcome → learning.

این سند باید مرجع وضعیت پروژه در تاریخ 2026-08-25 باشد.
