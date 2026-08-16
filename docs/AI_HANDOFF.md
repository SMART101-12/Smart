# SMART AI HANDOFF — Read This First

این فایل یک قرارداد عملیاتی برای هوش مصنوعی بعدی است.

## پروژه چیست؟
SMART یک موتور تحلیل و تصمیم‌یار بازار ایران است. هدف، پیش‌بینی روزانه و سپس ساخت Entry/Exit بر اساس شواهد قابل بک‌تست است.

## قانون اصلی
نتیجه مهم‌تر از ادعا است. هر مدل باید با baseline مقایسه شود و نتیجه واقعی آن در Git ثبت شود.

## قبل از هر کاری
این فایل‌ها را بخوان:
1. `docs/SMART_MASTER_ROADMAP.md`
2. `docs/DAILY_PREDICTION_LEARNING.md`
3. `docs/INDICATOR_ENSEMBLE_EXPERIMENT_PLAN.md`
4. `docs/LEARNING_MEMORY_PROTOCOL.md`
5. `docs/FINAL_MODEL_ROADMAP.md`
6. `docs/EXPERIMENT_RESULTS.md`

سپس آخرین CI، آخرین commit و آخرین artifactهای `runtime/experiments` را بررسی کن.

## چه چیزهایی قبلاً شکست خورده‌اند؟
- SMART v1 از Naive بهتر نبود و نباید به‌عنوان مدل نهایی استفاده شود.
- یک خطای بک‌تست در هم‌ترازی signal day و entry day کشف شد.
- وابستگی calendar و dependencyهای CI باعث شکست تست شدند و باید قبل از ادعای نتیجه بررسی شوند.
- Win Rate به‌تنهایی معیار انتخاب نیست.
- هدف 99٪ نباید با leakage یا overfit دنبال شود.

## اکنون روی چه چیزی کار می‌کنیم؟
- Ichimoku
- حدود 200 indicator variants
- single / pairwise / triple / ensemble
- model-of-models
- Walk-Forward
- Frozen Out-of-Sample
- learning memory برای موفقیت و شکست

## نحوه کار
`Observe → Predict → Record → Reveal Actual → Diagnose Error → Learn → Next Day`

## ممنوع
- استفاده از آینده در feature
- tuning روی OOS
- حذف آزمایش شکست‌خورده از history
- ادعای عملکرد بدون artifact
- تغییر مدل بدون version/experiment record
- گزارش «بهتر شد» بدون مقایسه عددی با baseline

## خروجی هر مرحله
باید شامل باشد:
- مدل
- تعداد روزهای تست
- MAE
- Direction Accuracy
- Profit Factor در صورت وجود strategy
- Drawdown
- نسبت به baseline
- OOS
- خطای اصلی
- اصلاح
- اثر اصلاح
- Promote/Reject

## نقش هوش مصنوعی
هوش مصنوعی باید مانند مدیر تحقیق و توسعه کمی عمل کند: فرضیه بسازد، آزمایش کند، شکست را ثبت کند، از شکست یاد بگیرد و فقط مدل‌هایی را ارتقا دهد که در داده ندیده نیز شواهد کافی دارند.
