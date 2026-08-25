# SMART V2 — معماری کامل برنامه و مسیر داده

## 1. هدف معماری

هدف SMART V2 این است که داده بازار را به صورت قابل ردیابی و قابل اعتبارسنجی از منبع دریافت کند، سپس به شکل استاندارد پردازش کند، کیفیت را کنترل کند، شاخص‌ها و تحلیل‌ها را بسازد، سیگنال تولید کند و نتیجه سیگنال را برای یادگیری آینده ذخیره کند.

اصل کلیدی:

```text
Source Evidence
    ↓
Acquisition
    ↓
Raw
    ↓
Identity + Calendar
    ↓
Validation
    ↓
Processing / Normalization
    ↓
Monitored Dataset
    ↓
Indicators
    ↓
Score / Ensemble
    ↓
Signal
    ↓
Outcome 1D / 3D / 5D
    ↓
Learning / Weight Update
```

## 2. ساختار کد

```text
src/
├── smart/                 # اجزای legacy و adapterهای موجود
└── smart_v2/
    ├── acquisition/       # دریافت داده
    ├── core/              # قراردادها و مدل‌های پایه
    ├── validation/        # کنترل کیفیت و gap detection
    ├── processing/        # تبدیل raw به dataset پردازش‌شده
    ├── analysis/          # تحلیل و مشتقات تحلیلی
    └── ai/                # مرز اتصال مدل AI
```

### `src/smart`

این بخش هنوز برای اجزای موجود مانند TSETMC adapter نقش منبع زیرساختی دارد. V2 فعلاً به جای بازنویسی کامل acquisition از آن استفاده می‌کند.

### `src/smart_v2/core`

مسئول تعریف مدل‌ها و قراردادهای مشترک بین لایه‌ها است. این قسمت باید در آینده محل تعریف schema/version/metadataهای canonical باشد.

### `src/smart_v2/acquisition`

مسئول دریافت است و نباید تحلیل یا normalization انجام دهد.

فایل‌های اصلی:

- `service.py`
- `marketwatch_splitter.py`

### `src/smart_v2/validation`

مسئول تشخیص کیفیت داده، روزهای بسته بازار، gap و طبقه‌بندی رکوردها است.

فایل‌های اصلی:

- `history_quality.py`
- `validators.py`
- `repository.py`
- `runner.py`

### `src/smart_v2/processing`

در حال حاضر extraction اولیه از رکوردهای بازار را انجام می‌دهد. باید در مرحله بعد به normalization و canonical dataset کامل تبدیل شود.

### `src/smart_v2/analysis`

در وضعیت فعلی تحلیل بسیار محدود است و `daily_return` را تولید می‌کند. این لایه محل اصلی توسعه indicators و scoring خواهد بود.

### `src/smart_v2/ai`

فعلاً boundary اتصال مدل است. هنوز feature engineering، model registry، calibration، prediction history و learning loop کامل نشده‌اند.

## 3. ساختار داده پیشنهادی

### Raw

```text
runtime/market_raw/
```

داده خام باید immutable و قابل استناد باشد.

### Processed

```text
runtime/market_processed/
```

داده مشتق‌شده و استانداردشده از raw.

### Monitored

```text
runtime/market_monitored/
```

رکوردهای روزانه آماده تحلیل، همراه با quality flags و market-calendar status.

### Analysis

```text
runtime/analysis/
```

خروجی تحلیل‌ها و مشتقات تحلیلی.

### AI

```text
runtime/ai/
```

خروجی‌ها و artifactهای مرتبط با AI/learning که باید قابل بازتولید باشند.

### Future

```text
runtime/signals/
runtime/outcomes/
runtime/learning/
```

این سه لایه هنوز باید به صورت رسمی وارد معماری عملیاتی شوند.

## 4. Identity

هر رکورد باید در نهایت به identity پایدار instrument متصل شود:

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

در معماری فعلی identity enrichment کامل نشده و اتکا به نام نماد به تنهایی نباید برای instrumentهای مشابه مجاز باشد.

## 5. Calendar

تقویم بازار جزء داده کیفیت است و نباید با data absence اشتباه شود.

SMART باید حداقل این موارد را تشخیص دهد:

- روز کاری
- پنجشنبه/جمعه تعطیل
- تعطیلی رسمی
- تعطیلی استثنایی
- بازار/نوع instrument
- روز دارای رکورد صفر معامله

## 6. Quality Gate

قبل از ورود داده به analysis باید حداقل این gateها اعمال شوند:

1. schema معتبر
2. تاریخ معتبر
3. symbol/identity معتبر
4. منبع مشخص
5. عدم duplicate ناخواسته
6. calendar status مشخص
7. فیلدهای ضروری موجود
8. رکورد stale/missing مشخص
9. zero-trade با closed-day اشتباه نشود
10. provenance قابل ردیابی باشد

## 7. Analysis Pipeline آینده

حداقل گروه‌های شاخص:

- trend / moving averages
- momentum
- volatility
- volume/value
- money-flow / smart-money proxy
- support/resistance
- market breadth در صورت وجود داده کافی
- cross-asset inputs مانند دلار و طلا برای سناریوهای مربوط

هر score باید این metadata را نگه دارد:

```text
model_version
indicator_config_version
weight_version
source_date
symbol
data_quality_status
```

## 8. Signal Contract

سیگنال production-ready باید شامل این موارد باشد:

- symbol
- timestamp/date
- score
- confidence
- reasons
- entry zone
- invalidation/stop condition
- target/exit logic
- risk/reward
- data quality
- model version
- weight version

بدون داده کافی، سیستم نباید confidence بالا تولید کند.

## 9. Learning Loop

بعد از تولید سیگنال باید outcome آن ثبت شود:

```text
Signal at T
  ↓
Outcome T+1 trading day
  ↓
Outcome T+3 trading days
  ↓
Outcome T+5 trading days
  ↓
Performance by indicator
  ↓
Weight evaluation
  ↓
Candidate new weights
  ↓
Backtest / validation
  ↓
Promotion of new weight version
```

وزن‌ها نباید مستقیم و بدون validation تغییر کنند.

## 10. وضعیت معماری فعلی

معماری لایه‌ای **وجود دارد**؛ اما pipeline end-to-end هنوز **کامل و production-ready نیست**.

مهم‌ترین فاصله‌ها:

```text
Acquisition       ███████░░░  پایه خوب
Validation        ███████░░░  پایه قوی، پوشش ناقص
Processing        ████░░░░░░  اولیه
Analysis          ██░░░░░░░░  بسیار اولیه
Indicators        █░░░░░░░░░  عملاً در V2 کامل نشده
Scoring           █░░░░░░░░░  نیازمند توسعه
Signals           █░░░░░░░░░  نیازمند توسعه
Outcomes          █░░░░░░░░░  نیازمند توسعه
Learning          █░░░░░░░░░  نیازمند توسعه
Daily Product     ██░░░░░░░░░  نیازمند orchestration
```

این سند نقشه معماری فنی SMART V2 است و باید همراه با `SMART_V2_STATUS_2026-08-25.md` خوانده شود.
