# SMART V2 — برنامه تست و معیار پذیرش

## 1. اصل

هیچ بخش جدیدی از SMART V2 نباید فقط با اجرای موفق یک unit test پذیرفته شود. پذیرش باید چندلایه باشد:

```text
Static / Import
→ Unit
→ Integration
→ Data Quality
→ Historical Validation
→ End-to-End
→ Regression
→ CI
```

## 2. وضعیت تست موجود

در repository تست‌های V2 زیر وجود دارند:

- `tests/v2/test_ai.py`
- `tests/v2/test_analysis.py`
- `tests/v2/test_history_quality.py`
- `tests/v2/test_marketwatch_splitter.py`
- `tests/v2/test_processing.py`
- `tests/v2/test_processing_dataset.py`
- `tests/v2/test_validation.py`

علاوه بر آنها مجموعه تست‌های legacy/general نیز در `tests/` وجود دارد.

## 3. CI فعلی

Workflow:

```text
.github/workflows/v2-validation.yml
```

دستور اصلی تست:

```powershell
$env:PYTHONPATH = ".\src"
python -m pytest -q tests/v2
```

آخرین اجرای ثبت‌شده برای commit `66445151` در 2026-08-24 نتیجه **FAIL** داشته است.

بنابراین تا رفع failure، V2 نباید به عنوان test-green اعلام شود.

## 4. اولین تست اجباری

روی Windows/PowerShell:

```powershell
$env:PYTHONPATH = ".\src"
python -m pytest -q tests/v2
```

بعد:

```powershell
python -m pytest -q
```

هدف اول مشخص کردن دقیق test failure فعلی است، نه افزودن قابلیت جدید.

## 5. Acquisition tests

باید ثابت شود:

- TSETMC adapter بدون تغییر ناخواسته قابل استفاده است.
- symbol فارسی درست resolve می‌شود.
- encoding فارسی خراب نمی‌شود.
- MarketWatch header به شکل robust استخراج می‌شود.
- duplicate symbol به صورت قابل تشخیص گزارش می‌شود.
- raw response بدون دستکاری ذخیره می‌شود.
- خطای شبکه باعث ثبت داده جعلی نمی‌شود.

## 6. Processing tests

باید بررسی شود:

- input schema معتبر است.
- output schema پایدار است.
- close / last price / volume / trade count / trade value درست استخراج می‌شوند.
- missing values به شکل شفاف مدیریت می‌شوند.
- هیچ مقدار ساختگی تولید نمی‌شود.
- processing نسخه‌پذیر و reproducible است.

## 7. Validation tests

باید بررسی شود:

- روزهای پنجشنبه/جمعه به عنوان نبود داده اشتباه تفسیر نشوند.
- تعطیلات رسمی از missing data جدا شوند.
- exceptional closure از weekly closure جدا شود.
- zero-trade record از missing record جدا شود.
- gap واقعی شناسایی شود.
- تاریخ‌های خارج از محدوده حذف یا flag شوند.
- calendar overrideها درست اعمال شوند.

## 8. Historical validation

برای هر instrument مهم:

```text
rows
present dates
candidate dates
closed dates
expected trading dates
missing expected
zero trade
```

باید ثبت شود.

برای PALAYESH، معیار پذیرش تاریخی قبلی شامل بررسی 1427 رکورد و نبود missing expected بوده است؛ با این حال workflow فعلی باید دوباره پس از سبز شدن unit tests اجرا شود.

## 9. Analysis tests

فعلاً `daily_return` وجود دارد. تست‌های لازم برای آینده:

- first observation باید return تهی داشته باشد.
- close صفر باعث تقسیم بر صفر نشود.
- ترتیب زمانی داده‌ها صحیح باشد.
- gap در تقویم باعث محاسبه اشتباه return نشود.
- precision و نوع عددی پایدار باشد.

بعد از اضافه شدن indicators باید برای هر indicator تست deterministic و edge-case نوشته شود.

## 10. Signal tests

برای موتور آینده:

- score قابل بازتولید باشد.
- weight version در خروجی ثبت شود.
- داده ناقص confidence را محدود کند.
- entry/exit/stop منطق مشخص داشته باشند.
- risk/reward محاسبه معتبر باشد.
- signal بدون provenance قابل قبول نباشد.

## 11. Learning tests

باید ثابت شود:

- outcome فقط از آینده نسبت به signal استفاده می‌کند.
- look-ahead bias وجود ندارد.
- روزهای بسته بازار در T+1/T+3/T+5 درست محاسبه می‌شوند.
- تغییر وزن بدون validation وارد production نمی‌شود.
- هر مدل/وزن version قابل بازتولید است.

## 12. End-to-End acceptance

معیار اصلی پذیرش V2:

```text
TSETMC/MarketWatch
→ raw snapshot
→ identity
→ validation
→ processed record
→ monitored record
→ indicators
→ score
→ signal
→ outcome
→ learning record
```

برای حداقل یک نماد واقعی باید کل مسیر با artifactهای قابل مشاهده و provenance کامل اجرا شود.

## 13. CI acceptance gate

تا وقتی این موارد برقرار نشده‌اند، merge/promotion انجام نشود:

- `pytest tests/v2` = PASS
- full regression = PASS
- historical validation = PASS
- no unexpected data gaps
- no schema drift
- no encoding regression
- no duplicate identity ambiguity

## 14. ترتیب اجرای تست‌ها

1. رفع failure فعلی `tests/v2`
2. اجرای full test suite
3. تست acquisition با داده واقعی/fixture
4. تست historical quality
5. PALAYESH validation
6. processing dataset integration
7. end-to-end pipeline
8. regression
9. CI green
10. سپس توسعه indicator/score/signal

اصل مهم: **توسعه قابلیت‌های معاملاتی جدید قبل از سبز شدن validation pipeline انجام نشود.**
