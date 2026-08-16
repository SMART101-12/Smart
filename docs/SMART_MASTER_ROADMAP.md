# SMART — Master Roadmap, Decision Log & Handoff Specification

> نسخه مرجع پروژه برای هر هوش مصنوعی، توسعه‌دهنده یا تحلیلگری که بعداً وارد پروژه می‌شود.
>
> اصل: این فایل فقط «برنامه آینده» نیست؛ باید مسیر واقعی تصمیم‌ها، خطاها، اصلاحات، نتایج تست‌ها و معیار ارتقای مدل را در کنار Experiment Logs حفظ کند.

---

## 1. مأموریت SMART

SMART یک موتور تحلیل و تصمیم‌یار برای بازار ایران است که هدف نهایی آن تولید تحلیل روزانه قابل آزمون برای نمادها، تشخیص رژیم بازار، پیش‌بینی جهت/محدوده قیمت، و در مرحله نهایی پیشنهاد Entry / Stop / Target / Exit است.

SMART نباید صرفاً یک اسکور تکنیکال باشد. هر ادعای عملکرد باید با داده تاریخی point-in-time، Walk-Forward و Out-of-Sample قابل بازتولید باشد.

### هدف اصلی کاربر
نتیجه عملکرد مهم‌تر از زیبایی الگوریتم است. مسیر رسیدن به مدل نهایی باید قابل ردیابی باشد و هر مدل ضعیف یا شکست‌خورده نیز ثبت شود.

### خط قرمز
هیچ مدل یا گزارشی نباید با استفاده از اطلاعات آینده، look-ahead، survivor bias یا انتخاب مدل بر اساس OOS فریبنده ساخته شود.

---

## 2. وضعیت فعلی پروژه

نماد Validation اصلی: **پالایش**.

داده تاریخی موجود در Git از اولین رکورد معتبر نماد برای آزمایش‌های walk-forward استفاده می‌شود؛ تاریخ غیرمعاملاتی یا missing نباید به‌عنوان جلسه معاملاتی تلقی شود.

داده و نتایج باید داخل Git versioned باشند.

---

## 3. مسیر واقعی طی‌شده تا این نسخه

### مرحله 0 — زیرساخت داده
- ذخیره داده تاریخی در Git.
- استفاده از داده point-in-time.
- نیاز به Trading Calendar برای حذف تعطیلات و gapهای غیرواقعی.
- داده بیرون از Git نباید برای تولید قیمت وارد مدل شود وقتی آزمایش بر مبنای Git تعریف شده است.

### مرحله 1 — SMART v1 / Daily Prediction
ایده اولیه: استفاده از Trend، SMA/EMA، Momentum و یادگیری روزانه برای پیش‌بینی روز بعد.

نتیجه ثبت‌شده: **رد شد**.

دلیل: در آزمایش تاریخی، عملکرد آن از baseline ساده Naive بهتر نبود. بنابراین پیچیدگی اضافی بدون ارزش پیش‌بینی پذیرفته نشد.

### مرحله 2 — تعریف موتور یادگیری روزانه
چرخه استاندارد شد:

`داده تا T → پیش‌بینی T+1 → مشاهده T+1 → محاسبه خطا → Error Analysis → یادگیری → T+1`

برای هر روز باید قیمت پیش‌بینی، بازده، جهت، محدوده High/Low، confidence، regime، feature snapshot، نسخه موتور و rationale ثبت شود.

### مرحله 3 — Ichimoku و Ensemble
Ichimoku به موتور اضافه شد و برنامه آزمایش سیستماتیک حدود 200 variant اندیکاتوری تعریف شد.

خانواده‌ها شامل Trend، Momentum، Volume، Volatility، Price Action، Moving Average، Oscillator، Money Flow، Ichimoku و اجزای آن و سایر features هستند.

### مرحله 4 — آزمایش ترکیبی
طرح فعلی:
- single indicators
- pairwise
- triples
- small ensembles
- model-of-models
- regime-conditioned ensembles
- frozen OOS

ترکیب برنده یک مرحله دوباره با ترکیب‌های برنده تست می‌شود.

---

## 4. اشتباهات مهمی که قبلاً کشف شد و نباید تکرار شوند

### خطای A — اتکا به Win Rate
Win Rate به‌تنهایی معیار مدل خوب نیست. باید MAE/RMSE، Direction Accuracy، Profit Factor، Expectancy، Drawdown و پایداری OOS هم بررسی شوند.

### خطای B — قیمت ورود نادرست در بک‌تست
در نسخه اولیه بک‌تست، سیگنال روز T با قیمت همان روز و entry_date روز T+1 قاطی شده بود. این می‌تواند عملکرد را مخدوش کند. Entry باید دقیقاً بر اساس اطلاعات و قیمت قابل معامله در T+1 تعریف شود.

### خطای C — مدل پیچیده‌تر الزاماً بهتر نیست
SMART v1 نشان داد که مدل ساده می‌تواند به مدل پیچیده نزدیک یا بهتر باشد. هر feature باید ارزش افزوده خود را در تست خارج از نمونه ثابت کند.

### خطای D — خطر overfitting
انتخاب بر اساس کل تاریخ ممنوع است. Test/OOS باید برای مدل نهایی فریز بماند.

### خطای E — مشکل تقویم و gap
تعطیلات رسمی، پنجشنبه/جمعه و تعطیلی نماد نباید به‌عنوان missing data یا جلسه معاملاتی اشتباه تشخیص داده شوند. Calendar باید symbol-aware و market-type-aware باشد.

### خطای F — CI / وابستگی‌ها
در مراحل قبلی کمبود dependency و dependency به فایل calendar مفقود باعث شکست تست شد. هر تغییر باید CI را قبل از ادعای نتیجه سبز کند.

### خطای G — ادعای دقت 99٪
99٪ هدف تضمین‌شده نیست. هدف واقعی، بهبود پایدار OOS نسبت به baseline و کنترل ریسک است. اگر داده چنین دقتی ندهد، باید همان نتیجه واقعی گزارش شود.

---

## 5. قرارداد داده

هر observation باید حداقل شامل:
- trading date
- close / adjusted close در صورت تعریف روشن
- high
- low
- volume / ارزش معاملات در صورت موجود بودن
- source / provenance
- symbol
- data quality flags

هیچ feature نباید از observation آینده استفاده کند.

### Corporate Actions
در صورت وجود افزایش سرمایه، سود نقدی، توقف، بازگشایی یا تغییر ساختار قیمت، raw و adjusted price باید از هم تفکیک شوند و اثر آن در backtest مستند شود.

---

## 6. Feature Store / حدود 200 اندیکاتور

اندیکاتورها باید به خانواده‌ها تقسیم شوند تا از تکرار اطلاعات جلوگیری شود:

1. Trend
2. Moving Average
3. Momentum
4. Oscillator
5. Volatility
6. Volume
7. Money Flow
8. Price Action
9. Breakout
10. Support/Resistance
11. Ichimoku
12. Regime

### Ichimoku
- Tenkan-sen
- Kijun-sen
- Senkou Span A
- Senkou Span B
- Cloud thickness
- Price vs Cloud
- Tenkan/Kijun cross
- Chikou relationship
- Cloud breakout

ویژگی‌های Ichimoku باید با منطق زمانی صحیح استفاده شوند؛ هیچ span آینده نباید به‌صورت اشتباه به روز تصمیم برگردد.

---

## 7. آزمایش مدل‌ها

### سطح A — Baseline
حداقل:
- Naive close
- Previous-return/momentum baseline
- Buy & Hold برای مقایسه سرمایه‌گذاری
- SMART v1

### سطح B — Single
هر variant اندیکاتوری جداگانه.

### سطح C — Pairwise
ترکیب‌های دو به دو. با حدود 200 variant، فضای خام می‌تواند نزدیک 20 هزار جفت باشد. اجرای کامل باید با cache، parallelization و ثبت immutable نتایج انجام شود.

### سطح D — Triple
بهترین pairها به triple تبدیل می‌شوند.

### سطح E — Ensemble
ترکیب‌های کوچک با کنترل complexity.

### سطح F — Model-of-Models
مدل‌های برتر با هم ترکیب و دوباره validation می‌شوند.

### سطح G — Frozen OOS
فقط مدل‌های منتخب بدون تغییر پارامتر روی داده کاملاً ندیده ارزیابی می‌شوند.

---

## 8. روش انتخاب مدل

مدل برنده با یک معیار انتخاب نمی‌شود.

### Forecast metrics
- MAE
- RMSE
- MAPE با احتیاط
- Direction Accuracy
- Up/Down precision/recall در صورت کافی بودن نمونه
- High/Low range coverage
- Calibration of confidence

### Trading metrics
- Profit Factor
- Expectancy
- CAGR/Total Return
- Max Drawdown
- Sharpe/Sortino در صورت تعریف مناسب
- Average Win/Loss
- MFE/MAE
- turnover
- number of trades

### Model quality
- OOS stability
- regime stability
- window stability
- complexity penalty
- sensitivity to parameters

---

## 9. Walk-Forward Protocol

برای هر پنجره:

`Train → Validate → Freeze → Test`

مدل فقط با Train/Validation انتخاب می‌شود. Test فقط یک‌بار برای ارزیابی نهایی پنجره مصرف می‌شود.

پس از پایان یک پنجره و آشکار شدن نتیجه واقعی، آن اطلاعات می‌تواند وارد حافظه آموزشی آینده شود.

---

## 10. Learning Memory

SMART باید هم موفقیت و هم شکست را ذخیره کند.

هر experiment record حداقل:
- experiment_id
- engine_version
- parent_model
- symbol
- feature_set
- parameters
- train/validation/test dates
- metrics
- baseline metrics
- regime
- decision: promote/reject/hold
- reason
- error taxonomy

### حافظه منفی
ترکیب‌های شکست‌خورده دور ریخته نمی‌شوند؛ برای جلوگیری از تکرار بی‌دلیل ثبت می‌شوند.

### قانون یادگیری
مدل نباید OOS را برای tuning مصرف کند.

---

## 11. Error Analysis

هر خطا باید تا حد امکان در یکی از این گروه‌ها قرار گیرد:

- regime error
- trend error
- momentum error
- volume error
- smart-money error
- breakout failure
- false reversal
- volatility error
- data/calendar error
- execution/entry error
- exit/target error

بعد از هر batch باید بررسی شود کدام خطا بیشترین هزینه را ایجاد کرده و آیا اصلاح آن در OOS نیز مفید است.

---

## 12. Entry / Exit Engine — بعد از اثبات Forecast

پیش‌بینی قیمت به‌تنهایی سیگنال معامله نیست.

### Entry types
- Breakout
- Pullback
- Reversal

### Entry باید شامل
- entry zone
- trigger
- invalidation
- liquidity condition
- volume confirmation
- confidence

### Stop
ترجیحاً ساختاری و volatility-aware:
- swing low/high
- ATR
- support/resistance
- regime volatility

### Target
- T1
- T2
- T3
- trailing stop
- break-even rule

هر rule باید جداگانه backtest شود.

---

## 13. Market Regime

مدل باید حداقل Bull / Bear / Sideways را تشخیص دهد و در صورت کفایت داده Volatility Regime را نیز لحاظ کند.

وزن اندیکاتورها می‌تواند regime-dependent باشد، اما این وزن‌ها فقط با اطلاعات گذشته همان پنجره یاد گرفته می‌شوند.

---

## 14. مسیر توسعه نسخه‌ها

### v2
Ichimoku + indicator ensemble + systematic testing.

### v3
Regime-conditioned ensembles + robust feature selection + better price-action features.

### v4
Entry/Stop/Target optimization جدا از Forecast.

### v5
Walk-forward adaptive learning و calibration confidence.

### v6
Multi-symbol validation: پالایش، عیار، سایر نمادهای بورس و صندوق‌ها با market schedule مناسب.

### v7
Production daily engine.

نسخه نهایی فقط زمانی frozen می‌شود که OOS و CI هر دو قابل قبول باشند.

---

## 15. معیار ارتقای نسخه

یک نسخه فقط وقتی Promote می‌شود که:
1. تست نرم‌افزاری سبز باشد.
2. Data Quality سبز باشد.
3. بهتر از baseline باشد یا دلیل اقتصادی روشنی برای trade-off داشته باشد.
4. OOS مثبت و پایدار باشد.
5. فقط روی یک پنجره برنده نباشد.
6. complexity نسبت به improvement منطقی باشد.
7. نتیجه قابل بازتولید باشد.
8. experiment record در Git ثبت شده باشد.

در غیر این صورت: **REJECT**.

---

## 16. ساختار پیشنهادی Git

```text
README.md
CHANGELOG.md

/docs/
  SMART_MASTER_ROADMAP.md
  DAILY_PREDICTION_LEARNING.md
  INDICATOR_ENSEMBLE_EXPERIMENT_PLAN.md
  LEARNING_MEMORY_PROTOCOL.md
  FINAL_MODEL_ROADMAP.md
  EXPERIMENT_RESULTS.md
  ERROR_LOG.md
  MODEL_CARD.md
  DATA_DICTIONARY.md

/src/smart/
  data/
  calendar/
  features/
  regime/
  models/
  ensemble/
  backtest/
  execution/
  learning/

/scripts/
  run_daily_prediction.py
  run_ensemble_experiments.py
  run_walk_forward.py
  validate_data.py

/runtime/experiments/<symbol>/
  experiment_*.json
  leaderboard.json
  errors.json
  final_candidate.json

/tests/
```

---

## 17. گزارش نهایی مورد انتظار برای کاربر

هر بار کاربر نتیجه می‌خواهد، پاسخ باید کوتاه اما عددی باشد:

1. مدل فعلی چیست؟
2. روی چند روز تست شده؟
3. Direction Accuracy؟
4. MAE؟
5. Profit Factor؟
6. Max Drawdown؟
7. نسبت به Naive چقدر بهتر/بدتر؟
8. OOS چگونه بوده؟
9. چه اشتباه اصلی پیدا شد؟
10. چه اصلاحی انجام شد؟
11. اصلاح روی OOS چه اثری گذاشت؟
12. مدل Promote یا Reject؟

از توضیح طولانی بدون نتیجه عددی خودداری شود.

---

## 18. دستورالعمل برای هوش مصنوعی بعدی

اگر این repository به هوش مصنوعی دیگری داده شد:

1. ابتدا این فایل را کامل بخوان.
2. سپس `FINAL_MODEL_ROADMAP.md`، `EXPERIMENT_RESULTS.md` و `ERROR_LOG.md` را بخوان.
3. آخرین CI و آخرین experiment artifact را بررسی کن.
4. هیچ ادعای عملکردی را بدون artifact/commit معتبر قبول نکن.
5. مدل‌های Reject شده را دوباره بدون دلیل تکرار نکن.
6. OOS فریز شده را دستکاری نکن.
7. قبل از تغییر مدل، baseline را دوباره مقایسه کن.
8. بعد از تغییر، تست unit، data validation، walk-forward و OOS مربوطه را اجرا کن.
9. نتیجه، خطا و تصمیم را در Git ثبت کن.
10. هرگز برای رسیدن به عدد هدف 99٪ داده آینده را وارد مدل نکن.

---

## 19. تعریف موفقیت نهایی

موفقیت SMART این نیست که روی تاریخ گذشته یک سود بزرگ نشان دهد.

موفقیت یعنی:

`Reliable Data → No Leakage → Repeatable Experiment → OOS Improvement → Controlled Risk → Explainable Decision → Continuous Learning`

و مدل نهایی باید بتواند برای هر تصمیم توضیح دهد:

**چه دید؟ چه پیش‌بینی کرد؟ چرا؟ چه اتفاقی افتاد؟ کجا اشتباه کرد؟ چه چیزی یاد گرفت؟ نسخه بعدی چه تغییری کرد؟ و آیا آن تغییر در داده ندیده هم بهتر بود؟**

این سند باید همراه پروژه باقی بماند و با هر تغییر معماری مهم به‌روزرسانی شود.
