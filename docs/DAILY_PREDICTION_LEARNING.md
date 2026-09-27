# SMART Daily Prediction & Learning Engine

## هدف
این سند مشخص می‌کند SMART چگونه از اولین روز معاملاتی معتبر موجود برای هر نماد، روزبه‌روز پیش‌بینی می‌کند، نتیجه واقعی را می‌گیرد، خطا را اندازه‌گیری می‌کند و فقط با اطلاعاتی که تا آن لحظه در دسترس بوده است یاد می‌گیرد.

## اصل غیرقابل مذاکره
هیچ داده‌ای از آینده نباید در پیش‌بینی روز T استفاده شود. نتیجه روز T+1 فقط بعد از ثبت پیش‌بینی T به موتور داده می‌شود.

## چرخه روزانه
1. دریافت تمام داده‌های معتبر تا پایان روز T.
2. محاسبه Features بدون look-ahead.
3. تعیین Market Regime و Stock Regime.
4. تولید پیش‌بینی روز T+1 شامل قیمت، بازده، جهت و بازه High/Low.
5. ثبت نسخه موتور، ویژگی‌ها، وزن‌ها و دلایل تصمیم.
6. در دسترس قرار گرفتن داده واقعی T+1، محاسبه خطا و نتیجه معامله فرضی.
7. طبقه‌بندی خطا: Trend / Momentum / Volume / Smart Money / Regime / Data / Entry-Exit.
8. به‌روزرسانی دانش موتور فقط با داده‌های تحقق‌یافته تا T+1.
9. حرکت به روز بعد.

## پیش‌بینی پنج‌روزه
برای هر تاریخ، افق‌های 1، 3 و 5 روزه ثبت می‌شوند. افق 5 روزه برای تحلیل مسیر است و نباید برای پیش‌بینی روزهای میانی از اطلاعات آینده استفاده کند.

## خروجی هر روز
- symbol
- trading_date
- current_price
- predicted_next_close
- predicted_return
- predicted_direction
- predicted_high_range
- predicted_low_range
- confidence
- market_regime
- stock_regime
- feature snapshot
- engine version
- model/weight version
- rationale

## ارزیابی
- Direction Accuracy
- MAE
- MAPE
- RMSE
- directional hit rate by regime
- range coverage
- 1/3/5-day forecast error
- profit factor
- expectancy
- max drawdown
- MAE/MFE

## یادگیری
SMART نباید برای رسیدن به عدد ظاهری 99% داده آینده را وارد آموزش کند. هدف، بیشینه‌کردن عملکرد خارج از نمونه و کاهش خطای پایدار است. هر تغییر در موتور باید با نسخه، تاریخ، دلیل، معیار قبل و بعد و نتیجه تست ثبت شود.

## Baseline
هر نسخه باید با حداقل این baselineها مقایسه شود:
- Naive: فردا = قیمت امروز
- Momentum ساده
- Buy & Hold برای عملکرد سرمایه‌گذاری

## مسیر پیشنهادی موتور
Data Quality -> Trading Calendar -> Market Regime -> Stock Regime -> Trend -> Momentum -> Volume/Money Flow -> Smart Money -> Price Action -> Forecast -> Entry/Stop/Targets -> Outcome -> Error Analysis -> Walk-Forward Learning.

## شروع داده
برای هر نماد از اولین روز معاملاتی معتبر موجود در Git شروع می‌شود؛ تاریخ‌های تعطیل، missing و غیرمعاملاتی وارد زنجیره پیش‌بینی نمی‌شوند.

## وضعیت
این سند قرارداد طراحی موتور است. نتایج واقعی باید در فایل‌های versioned خروجی و commitهای جداگانه ثبت شوند تا مشخص باشد هر نتیجه با کدام موتور تولید شده است.
