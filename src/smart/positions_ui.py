"""Explicitly reported holdings; no form submits brokerage orders."""
HTML = '''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SMART | پیگیری ورود و خروج</title>
<link rel="stylesheet" href="/dashboard.css"></head><body>
<header><a href="/">SMART · بازگشت به تحلیل</a></header><main>
<h1>دفتر موقعیت و بررسی خروج</h1>
<p class="notice">این صفحه سفارش ارسال نمی‌کند. ورود و فروش را پس از اجرای آزمایشی یا واقعی ثبت کنید.
بررسی خروج با درخواست شما و با کندلهای کامل انجام می‌شود؛ هشدار لحظه‌ای نیست.</p>
<p id="position-status" role="status" aria-live="polite"></p>
<section><h2>ثبت ورود انجام‌شده</h2><form id="position-open" class="layer-grid">
<label>نماد<input name="symbol" required maxlength="80"></label>
<label>نوع ثبت<select name="mode"><option value="PAPER">آزمایشی</option><option value="REPORTED_REAL">واقعی، گزارش‌شده توسط من</option></select></label>
<label>تاریخ ورود میلادی<input name="entry_date" type="date" required></label>
<label>قیمت ورود · ریال<input name="entry_price" type="number" min="0.000001" step="any" required></label>
<label>تعداد<input name="quantity" type="number" min="1" step="1" required></label>
<label>هزینه پرداخت‌شده ورود · ریال<input name="entry_fee" type="number" min="0" step="any" value="0" required></label>
<label>حد ضرر<input name="stop" type="number" min="0.000001" step="any" required></label>
<label>هدف اول<input name="tp1" type="number" min="0.000001" step="any" required></label>
<label>هدف دوم<input name="tp2" type="number" min="0.000001" step="any" required></label>
<button type="submit">ثبت ورود گزارش‌شده</button></form></section>
<section><h2>موقعیت‌ها</h2><button id="positions-refresh" type="button">بازخوانی دفتر</button>
<div id="positions-list"></div></section>
<section id="selected-position" hidden><h2 id="selected-title"></h2>
<p id="selected-info"></p><button id="position-review" type="button">دریافت تاریخچه و بررسی خروج</button>
<div id="position-review-result" role="status"></div>
<details><summary>ثبت فروش انجام‌شده</summary><form id="position-exit" class="layer-grid">
<label>تاریخ فروش میلادی<input name="fill_date" type="date" required></label>
<label>قیمت فروش · ریال<input name="price" type="number" min="0.000001" step="any" required></label>
<label>تعداد فروخته‌شده<input name="quantity" type="number" min="1" step="1" required></label>
<label>هزینه فروش · ریال<input name="fee" type="number" min="0" step="any" value="0" required></label>
<label>دلیل<select name="reason"><option value="MANUAL">تصمیم دستی</option><option value="TP1">هدف اول</option><option value="TP2">هدف دوم</option><option value="STOP">حد ضرر</option><option value="TIME">خروج زمانی</option></select></label>
<button type="submit">ثبت فروش گزارش‌شده</button></form></details>
<details><summary>افزایش حد ضرر برای روز آینده</summary><form id="position-stop" class="layer-grid">
<label>حد ضرر جدید<input name="stop" type="number" min="0.000001" step="any" required></label>
<label>اعمال از تاریخ میلادی<input name="effective_on" type="date" required></label>
<button type="submit">ثبت حد ضرر آینده</button></form></details>
<details><summary>رویدادها و بررسی‌های ثبت‌شده</summary><pre id="position-evidence"></pre></details>
</section></main><script src="/positions.js" defer></script></body></html>'''
