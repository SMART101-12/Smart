# SMART Custom Model v1 — MACD + RSI + Ichimoku + Bollinger + Moving Averages

## هدف
ساخت یک مدل اختصاصی SMART به‌جای اتکا به یک اندیکاتور منفرد. مدل باید سیگنال‌های چند خانواده را تلفیق کند و فقط وقتی سیگنال نهایی معتبر است وارد لایه Entry/Exit شود.

## اجزای مدل
### 1) Trend / Moving Averages
- SMA: 10, 20, 50, 100, 200
- EMA: 9, 21, 50, 100, 200
- شیب MA
- فاصله قیمت از MA
- کراس‌های مهم

### 2) MACD
- MACD line
- Signal line
- Histogram
- Histogram slope
- Zero-line state
- Cross state

### 3) RSI
- RSI 7 / 14 / 21
- خروج از oversold/overbought
- divergence در صورت تعریف بدون look-ahead
- RSI trend

### 4) Ichimoku
- Tenkan
- Kijun
- Senkou A/B
- Cloud thickness
- Price vs Cloud
- Tenkan/Kijun cross
- Cloud breakout
- Chikou relationship

### 5) Bollinger Bands
- Middle band
- Upper/lower band
- %B
- Band width
- Squeeze / expansion
- Breakout/reversion state

## منطق امتیازدهی اولیه
هر خانواده یک score مستقل از -100 تا +100 تولید می‌کند. سپس scoreها با وزن‌های قابل یادگیری ترکیب می‌شوند.

Initial equal-weight baseline:
- MA = 20%
- MACD = 20%
- RSI = 20%
- Ichimoku = 25%
- Bollinger = 15%

این وزن‌ها «مدل نهایی» نیستند و فقط baseline هستند. وزن‌های بهینه باید با Walk-Forward یاد گرفته شوند.

## Regime Gate
قبل از صدور سیگنال:
- Bull
- Bear
- Sideways
- High/Low volatility
تشخیص داده می‌شود.

وزن‌ها می‌توانند regime-dependent شوند، اما فقط با داده گذشته همان پنجره آموزش داده می‌شوند.

## Signal states
- STRONG_BUY
- BUY
- HOLD
- SELL
- STRONG_SELL
- NO_TRADE

NO_TRADE زمانی استفاده می‌شود که سیگنال‌ها conflict شدید داشته باشند یا confidence/liquidity کافی نباشد.

## Entry
Forecast و signal از Entry جدا هستند.
Entry باید trigger مشخص داشته باشد، مثلاً:
- breakout تأییدشده
- pullback به MA/Kijun/BB mid با برگشت momentum
- reversal تأییدشده

## Risk
هر سیگنال باید:
- entry zone
- invalidation/stop
- T1/T2/T3
- trailing rule
- max risk per trade
داشته باشد.

## تست
این مدل باید با:
1. Naive
2. SMART v1
3. E080
4. بهترین single
5. بهترین pair
6. بهترین ensemble
مقایسه شود.

تست‌ها:
- Walk-Forward
- regime breakdown
- parameter perturbation
- frozen OOS
- transaction-cost sensitivity

## معیار پذیرش
مدل فقط در صورت بهبود پایدار OOS، ریسک قابل قبول، عدم leakage و robustness به Candidate تبدیل می‌شود.

## نسخه
Custom Model v1 — specification only. نتایج تا قبل از اجرای واقعی آزمایش، معتبر تلقی نمی‌شوند.
