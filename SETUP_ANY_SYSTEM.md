# راه‌اندازی SMART روی هر سیستم

این فایل مسیر استاندارد نصب، تست و اجرای SMART را برای Windows، macOS، Linux
و Docker توضیح می‌دهد. برنامه در حالت تحلیل بازار به کلید OpenAI نیاز ندارد؛
فقط بخش توضیح ChatGPT به `OPENAI_API_KEY` نیاز دارد.

## پیش‌نیازها

- Python 3.11 یا جدیدتر
- Git
- دسترسی شبکه برای دریافت داده‌های TSETMC
- حداقل ۴ گیگابایت فضای آزاد برای محیط و داده‌های تاریخی

برای بررسی نسخهٔ Python:

```bash
python --version
```

در Windows اگر `python` روی PATH نیست، مسیر کامل مفسر را استفاده کنید؛ برای
نمونه:

```powershell
$py = "C:\Users\PC101\anaconda3\python.exe"
```

## نصب پیشنهادی با محیط مجازی

### Windows PowerShell

از ریشهٔ پروژه اجرا کنید:

```powershell
cd "C:\ مسیر پروژه\smart"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = ".\src"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

اگر اجرای اسکریپت PowerShell مسدود بود، فقط برای همین پنجره:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

اگر Anaconda دارید و `conda` شناخته نمی‌شود، فعال‌سازی را کنار بگذارید:

```powershell
$py = "C:\Users\PC101\anaconda3\python.exe"
$env:PYTHONPATH = ".\src"
& $py -m pip install -r .\requirements.txt
```

### macOS / Linux

```bash
cd /path/to/smart
python3.11 -m venv .venv
source .venv/bin/activate
export PYTHONPATH=./src
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## تست نصب

در ریشهٔ پروژه:

```bash
python -m pytest -q
```

تمام تست‌ها باید سبز باشند. تست‌ها به‌صورت پیش‌فرض به بازار وصل نمی‌شوند.

## اجرای داشبورد

```bash
export PYTHONPATH=./src       # macOS/Linux
# Windows PowerShell:
# $env:PYTHONPATH = ".\src"

python -m uvicorn smart.webapp:app --host 127.0.0.1 --port 8000
```

مرورگر را روی آدرس زیر باز کنید:

```text
http://127.0.0.1:8000/
```

دکمه‌های اصلی داشبورد:

1. «تحلیل نمادها»: تاریخچهٔ کامل موجود، MACD، RSI، SMA/MA، EMA، ATR، حجم،
   Smart Money و تصمیم چندعاملی را محاسبه می‌کند.
2. «آزمون walk-forward»: ۲۰ روز اول را تاریخچهٔ اولیه می‌گیرد و سپس تصمیم‌ها را
   در پنجره‌های ۳۰روزه ارزیابی می‌کند.
3. «حافظهٔ یادگیری»: بردها، باخت‌ها و دلیل شکست تصمیم‌های ثبت‌شده را نشان می‌دهد.
4. «توضیح با ChatGPT»: فقط در صورت تنظیم کلید OpenAI فعال می‌شود.

## تنظیم ChatGPT (اختیاری)

فایل نمونه را کپی کنید:

```bash
cp .env.example .env
```

سپس مقدار کلید را در `.env` وارد کنید:

```text
OPENAI_API_KEY=کلید-خودت
OPENAI_MODEL=gpt-5
```

فایل `.env` در Git ثبت نمی‌شود. در PowerShell می‌توانید به‌جای فایل:

```powershell
$env:OPENAI_API_KEY = "کلید-خودت"
$env:OPENAI_MODEL = "gpt-5"
```

## اجرای آزمون تاریخی از خط فرمان

برای یک فایل آرشیو JSON که کلید `daily_history` یا `records` دارد:

```bash
PYTHONPATH=./src python scripts/run_walk_forward_exam.py \
  path/to/archive.json \
  --symbol عیار \
  --initial-history 20 \
  --evaluation-window 30 \
  --output runtime/learning/عیار/cli_exam.json
```

در Windows PowerShell:

```powershell
$env:PYTHONPATH = ".\src"
python .\scripts\run_walk_forward_exam.py `
  .\path\to\archive.json `
  --symbol عیار `
  --initial-history 20 `
  --evaluation-window 30 `
  --output .\runtime\learning\عیار\cli_exam.json
```

## اجرای Docker

برای اجرای داشبورد:

```bash
docker build -t smart-market .
docker run --rm -p 8000:8000 -e PYTHONPATH=/app/src smart-market
```

برای سرویس MCP:

```bash
docker run --rm -p 8000:8000 \
  -e PYTHONPATH=/app/src \
  -e MCP_TRANSPORT=streamable-http \
  smart-market python -m smart.mcp_http
```

در استقرار ابری، `OPENAI_API_KEY` را فقط به‌عنوان Secret تنظیم کنید و آن را در
کد یا Git ننویسید.

## مسیرهای مهم خروجی

- `runtime/learning/<نماد>/decisions/`: تصمیم‌های نقطه‌ای و وضعیت pending/revealed
- `runtime/learning/<نماد>/outcomes/`: نتیجهٔ افشاشده و تحلیل دلیل برد/باخت
- `runtime/learning/<نماد>/exams/`: فایل کامل آزمون walk-forward
- `runtime/learning/<نماد>/strategy_memory.json`: خلاصهٔ عملکرد خانواده‌ها و دلایل شکست
- `runtime/analysis/`: گزارش‌های تحلیل ذخیره‌شده

## رفع خطاهای متداول

### `conda is not recognized`

از `conda activate` استفاده نکنید؛ مفسر کامل Anaconda را مستقیم صدا بزنید:

```powershell
$py = "C:\Users\PC101\anaconda3\python.exe"
& $py -m pip install -r .\requirements.txt
& $py -m pytest -q
& $py -m uvicorn smart.webapp:app --host 127.0.0.1 --port 8000
```

### `Python was not found`

Python 3.11+ را نصب کنید یا مسیر کامل `python.exe` را در دستورات بالا قرار دهید.

### خطای TSETMC

اتصال TSETMC ممکن است موقتاً محدود یا قطع باشد. خطا در خروجی `errors` نشان داده
می‌شود؛ دادهٔ ساختگی جایگزین دادهٔ واقعی نمی‌شود.

### پورت اشغال است

```bash
python -m uvicorn smart.webapp:app --host 127.0.0.1 --port 8001
```

سپس `http://127.0.0.1:8001/` را باز کنید.

## نکتهٔ پژوهشی

آزمون‌ها و رتبه‌بندی‌ها برای تحقیق و تصمیم‌یار هستند. بازده تاریخی، تضمین سود
آینده نیست؛ هزینهٔ معامله، لغزش قیمت، نقدشوندگی و محدودیت‌های بازار باید قبل از
هر استفادهٔ عملی جداگانه بررسی شوند.
