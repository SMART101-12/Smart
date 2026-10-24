"""Read-only company report explorer."""

HTML = '''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SMART | گزارش‌های کدال</title>
<link rel="stylesheet" href="/dashboard.css"></head><body>
<header><a href="/">SMART — بازگشت به تحلیل</a></header><main>
<h1>گزارش‌های مالی و فعالیت کدال</h1>
<p>فعالیت ماهانه، صورت‌های مالی تجمعی و عملکرد مستقل هر فصل. واحد و منبع کنار هر عدد آمده است.</p>
<section class="search"><label for="codal-symbol">نماد</label><div class="search-row">
<input id="codal-symbol" value="فولاد" maxlength="80"><button id="codal-local">گزارش ذخیره‌شده</button>
<button id="codal-sync">دریافت و تکمیل از کدال</button></div></section>
<p id="codal-status" role="status" aria-live="polite"></p><section id="codal-help" aria-live="polite"></section><div id="codal-results"></div>
<p>فروش ماهانه، سود خالص ماهانه نیست. فصل مستقل از تفاضل دوره‌های تجمعی سازگار محاسبه می‌شود؛
داده ناقص صفر در نظر گرفته نمی‌شود. گزارش‌های شرکت اصلی و تلفیقی جدا هستند.</p>
</main><script src="/codal-reports.js" defer></script></body></html>'''
