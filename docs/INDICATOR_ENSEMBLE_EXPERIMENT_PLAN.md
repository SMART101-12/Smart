# SMART Indicator Ensemble Experiment Plan — v2

## هدف
ساخت یک موتور پیش‌بینی point-in-time برای پالایش که بتواند حدود 200 اندیکاتور موجود/قابل محاسبه را به‌صورت نظام‌مند آزمایش کند، Ichimoku را نیز در هسته قرار دهد، ترکیب‌های دو اندیکاتوری و سپس ترکیب‌های چنداندیکاتوری را ارزیابی کند و از نتایج هر آزمایش یاد بگیرد.

## قانون طلایی
هیچ ویژگی، نرمال‌سازی، انتخاب اندیکاتور یا وزن‌دهی نباید از داده آینده استفاده کند. انتخاب مدل فقط با داده آموزشی همان پنجره انجام می‌شود. Test/Out-of-Sample تا پایان آزمایش دست‌نخورده می‌ماند.

## Ichimoku
ویژگی‌های اصلی:
- Tenkan-sen
- Kijun-sen
- Senkou Span A/B
- Cloud thickness
- Price vs Cloud
- Tenkan/Kijun cross
- Chikou relationship
- Cloud breakout / regime

برای جلوگیری از look-ahead، Senkou spans هنگام تصمیم‌گیری با منطق زمانی صحیح استفاده می‌شوند و هیچ مقدار آینده به feature روز تصمیم برنمی‌گردد.

## فضای آزمایش
مرحله A — Baselines:
1. Naive close
2. Momentum ساده
3. نسخه فعلی SMART v1

مرحله B — Single indicators:
هر اندیکاتور به تنهایی برای direction و return forecast تست می‌شود.

مرحله C — Pairwise:
تمام جفت‌های مجاز اندیکاتورها به‌صورت دو به دو آزمایش می‌شوند. ترکیب‌هایی که اطلاعات تکراری شدید دارند با ثبت دلیل حذف می‌شوند، نه با حذف خاموش.

مرحله D — Triples / small ensembles:
از بهترین pairها، ترکیب‌های سه‌تایی و سپس گروه‌های کوچک ساخته می‌شود.

مرحله E — Regime-conditioned ensembles:
وزن/انتخاب اندیکاتورها بر اساس Bull / Bear / Sideways و در صورت کفایت داده بر اساس Volatility Regime انجام می‌شود.

مرحله F — Final ensemble:
فقط ترکیب‌هایی که در Walk-Forward و Out-of-Sample نسبت به baseline بهبود پایدار دارند اجازه ارتقا دارند.

## معیارهای رتبه‌بندی
هیچ مدل فقط با یک معیار انتخاب نمی‌شود. معیارها:
- Direction Accuracy
- MAE
- RMSE
- MAPE
- Hit rate برای بازده مثبت/منفی
- Range coverage
- Profit Factor
- Expectancy
- Max Drawdown
- تعداد معاملات/سیگنال
- پایداری بین regimeها
- پایداری بین پنجره‌های Walk-Forward

## جلوگیری از overfitting
- محدودیت تعداد featureها در ensemble
- جریمه پیچیدگی
- Walk-Forward validation
- آزمون Out-of-Sample فریز شده
- مقایسه با Naive و مدل قبلی
- ثبت همه آزمایش‌ها، حتی شکست‌خورده‌ها
- عدم انتخاب مدل بر اساس بهترین یک پنجره

## حافظه/یادگیری موتور
هر آزمایش یک رکورد immutable دارد:
experiment_id, engine_version, feature_set, parameters, train_window, validation_window, test_window, metrics, decision, reason, parent_model.

موتور از آزمایش‌ها یاد می‌گیرد اما test آینده را برای تنظیم مدل مصرف نمی‌کند. یادگیری شامل:
- وزن/اهمیت شرطی اندیکاتورها
- ترکیب‌های پایدار
- ترکیب‌های شکست‌خورده
- regime-specific performance
- خطاهای پرتکرار

## خروجی مورد انتظار
برای هر نسخه:
1. بهترین single indicators
2. بهترین pairها
3. بهترین triple/ensemble
4. اثر Ichimoku به تنهایی
5. اثر Ichimoku در ترکیب با هر خانواده
6. مقایسه با SMART v1 و Naive
7. دلیل ارتقا یا رد
8. مدل منتخب و نسخه آن

## مسیر اجرا
Palayesh از اولین رکورد معتبر Git شروع می‌شود. پس از اجرای کامل آزمایش‌ها، فقط مدل برنده‌ای که در تست خارج از نمونه نیز پایدار باشد به عنوان candidate final معرفی می‌شود.
