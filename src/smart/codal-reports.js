'use strict';
const codalNode = (tag, text) => { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; return n; };
const codalNumber = v => v == null ? 'دریافت نشده' : Number(v).toLocaleString('fa-IR', {maximumFractionDigits: 3});
const codalBasis = v => v === 'consolidated' ? 'تلفیقی' : 'شرکت اصلی';
function codalCell(cell) {
    const td = codalNode('td');
    td.append(codalNode('span', codalNumber(cell?.normalized_value ?? cell?.value) + ' ' + (cell?.normalized_unit || cell?.unit || '')));
    const refs = cell?.source_records || (cell?.source_url ? [{source_url: cell.source_url, report_id: cell.document_id}] : []);
    for (const ref of refs) {
        try {
            const url = new URL(ref.source_url);
            if (url.protocol !== 'https:' || !['www.codal.ir', 'codal.ir'].includes(url.hostname) || url.username || url.password) continue;
            const a = codalNode('a', ' [سند ' + (ref.report_id || '') + ']');
            a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; td.append(a);
        } catch (_) { /* Preserve the value without creating an invalid link. */ }
    }
    if (cell?.source_type === 'CALCULATED') td.append(codalNode('small', ' — محاسبه‌شده'));
    return td;
}
function codalTable(root, title, headers, rows) {
    const section = codalNode('section'), table = codalNode('table'), tr = codalNode('tr');
    section.append(codalNode('h2', title));
    if (!rows.length) { section.append(codalNode('p', 'هنوز گزارشی استخراج نشده است؛ وضعیت دریافت و خطاها را بررسی کنید.')); root.append(section); return; }
    headers.forEach(h => tr.append(codalNode('th', h))); const head = codalNode('thead'); head.append(tr); table.append(head);
    const body = codalNode('tbody');
    rows.forEach(row => { const r = codalNode('tr'); row.forEach(c => r.append(typeof c === 'object' && c !== null ? codalCell(c) : codalNode('td', c))); body.append(r); });
    table.append(body); const wrap = codalNode('div'); wrap.style.overflowX = 'auto'; wrap.append(table); section.append(wrap); root.append(section);
}
function renderCodal(data) {
    renderCodalAssistance(data);
    const root = document.getElementById('codal-results'); root.replaceChildren();
    const reports = data.financial_data || [];
    const metric = (r, key) => ({...r.metrics[key], source_url: r.metrics[key]?.source_url || r.source_url, document_id: r.document_id});
    codalTable(root, 'فعالیت ماهانه', ['دوره', 'فروش', 'انتشار', 'محصولات'], (data.monthly_sales || []).slice().reverse().map(r => [r.period, r.sales_value, r.publish_date, String(r.products.length)]));
    codalTable(root, 'صورت‌های مالی سالانه و میان‌دوره‌ای (تجمعی)', ['پایان دوره', 'ماه', 'مبنا', 'حسابرسی', 'درآمد', 'سود خالص', 'دارایی', 'بدهی', 'جریان نقد عملیاتی'], reports.slice().reverse().map(r => [r.period, String(r.months), codalBasis(r.basis), r.audited ? 'شده' : 'نشده', ...['revenue','net_profit','assets','liabilities','operating_cash_flow'].map(k => metric(r,k))]));
    codalTable(root, 'عملکرد مستقل هر فصل مالی', ['سال مالی', 'فصل', 'مبنا', 'درآمد', 'سود ناخالص', 'سود عملیاتی', 'سود خالص'], (data.quarterly_financials || []).slice().reverse().map(r => [r.fiscal_year_end, String(r.quarter), codalBasis(r.basis), ...['revenue','gross_profit','operating_profit','net_profit'].map(k => r.metrics[k])]));
    codalTable(root, 'جزئیات محصول و فروش ماهانه', ['دوره', 'محصول', 'بازار', 'مبلغ فروش', 'مقدار فروش', 'تولید', 'نرخ فروش'], (data.product_sales || []).slice().reverse().map(r => [r.period, r.product, {domestic:'داخلی',export:'صادراتی',services:'خدمات',returns:'برگشت فروش'}[r.market] || r.market, ...['sales_value','sales_quantity','production_quantity','selling_price'].map(k => r.metrics[k] || {})]));
    const details = codalNode('details'); details.append(codalNode('summary', 'پوشش داده و خطاهای دریافت'));
    details.append(codalNode('pre', JSON.stringify({quality:data.data_quality, sync:data.sync, issues:data.issues}, null, 2))); root.append(details);
}
function renderCodalAssistance(data) {
    const box = document.getElementById('codal-help'); if(!box) return;
    box.replaceChildren();
    const assistance = data.assistance || {};
    if(assistance.status === 'WAITING_FOR_USER') {
        box.append(codalNode('h2', 'برای ادامه دریافت، کمک شما لازم است'));
        box.append(codalNode('p', 'کدال تأیید کاربر می‌خواهد. تصویر را دریافت کنید و کد را وارد کنید. با تأیید، دریافت و ذخیره گزارش‌ها ادامه پیدا می‌کند؛ گزارش‌های قبلی حفظ می‌شوند.'));
        const image = codalNode('img'); image.alt = 'تصویر کد امنیتی کدال'; image.hidden = true;
        const refresh = codalNode('button', 'دریافت / تعویض تصویر'); refresh.type = 'button';
        const form = codalNode('form'), label = codalNode('label', 'کد تصویر: '), input = codalNode('input');
        input.id = 'codal-captcha-code'; label.htmlFor = input.id; input.maxLength = 10; input.autocomplete = 'off'; input.required = true;
        const submit = codalNode('button', 'تأیید کد و ادامه دریافت'); submit.type = 'submit';
        const message = codalNode('p');
        const payload = {symbol:data.symbol, session_id:assistance.session_id};
        const post = async (route, value) => {
            const response = await fetch('/api/codal-assistance/' + route, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
            const result = await response.json(); if(!response.ok) throw Error(result.detail || 'دریافت ناموفق'); return result;
        };
        refresh.onclick = async () => {
            refresh.disabled = true; submit.disabled = true; input.value = '';
            try { const result = await post('image',payload); image.src = result.image; image.hidden = false; message.textContent = 'کد تصویر را وارد کنید.'; }
            catch(e) { message.textContent = e.message + ' — اگر نشست منقضی شده، «دریافت و تکمیل از کدال» را بزنید.'; }
            finally { refresh.disabled = false; submit.disabled = false; }
        };
        form.onsubmit = async event => {
            event.preventDefault(); if(submit.disabled) return;
            submit.disabled = true; refresh.disabled = true;
            const controls = ['codal-local','codal-sync'].map(id => document.getElementById(id)); controls.forEach(b => b.disabled = true);
            message.textContent = 'در حال تأیید و ادامه دریافت…';
            try {
                const result = await post('verify',{...payload,code:input.value.trim()}); input.value = '';
                if(!result.verified) { message.textContent = 'کد پذیرفته نشد؛ تصویر جدید بگیرید و دوباره وارد کنید.'; return; }
                renderCodal(result.reports);
                document.getElementById('codal-status').textContent = 'تأیید انجام شد؛ گزارش‌های دریافت‌شده ذخیره و نمایش داده شدند. وضعیت تکمیل را بررسی کنید.';
            } catch(e) { message.textContent = e.message; }
            finally { submit.disabled = false; refresh.disabled = false; controls.forEach(b => b.disabled = false); }
        };
        form.append(label,input,submit); box.append(image,refresh,form,message);
    } else if(assistance.status === 'SESSION_EXPIRED') {
        box.append(codalNode('p','دریافت قبلی منتظر تأیید کاربر بود، اما نشست آن پایان یافته است. «دریافت و تکمیل از کدال» را بزنید تا نشست تازه ایجاد شود؛ فایل‌های ذخیره‌شده دوباره دریافت نمی‌شوند.'));
    } else if(assistance.status === 'UNSUPPORTED_CHALLENGE') {
        box.append(codalNode('p','کدال تأییدی با قالب پشتیبانی‌نشده نشان داده است. دریافت متوقف شده و گزارش‌های قبلی محفوظ‌اند.'));
    } else if(assistance.status === 'RATE_LIMITED') {
        box.append(codalNode('p','کدال موقتاً تعداد درخواست‌ها را محدود کرده است. پس از ' + new Date(assistance.retry_at).toLocaleString('fa-IR') + ' دوباره ادامه دریافت را بزنید. تحلیل از داده ذخیره‌شده استفاده می‌کند.'));
    }
    if(data.sync?.blocked_url) {
        try { const url = new URL(data.sync.blocked_url); if(url.protocol === 'https:' && ['www.codal.ir','codal.ir','search.codal.ir'].includes(url.hostname)) {
            const link = codalNode('a','مشاهده محل توقف در کدال'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; box.append(link);
        }} catch(_) { /* Do not display invalid external destinations. */ }
    }
}
async function loadCodal(sync) {
    const status = document.getElementById('codal-status');
    const buttons = ['codal-local','codal-sync'].map(id => document.getElementById(id)); buttons.forEach(b => b.disabled = true);
    status.textContent = sync ? 'در حال تکمیل گزارش‌ها؛ داده‌های دریافت‌شده ذخیره می‌شوند…' : 'در حال خواندن گزارش‌های ذخیره‌شده…';
    try {
        const symbol = document.getElementById('codal-symbol').value.trim();
        const response = await fetch('/api/company-reports?symbol=' + encodeURIComponent(symbol) + '&sync=' + sync);
        const data = await response.json(); if(!response.ok) throw Error(data.detail || 'دریافت ناموفق');
        renderCodal(data);
        status.textContent = data.sync?.status === 'SUCCESS' ? 'دریافت تکمیل شد؛ پوشش عددی هر دوره را در جدول‌ها بررسی کنید.' : 'گزارش‌های استخراج‌شده نمایش داده شد. دریافت هنوز کامل نیست؛ جزئیات خطا و پوشش در پایین صفحه است.';
    } catch(e) { status.textContent = 'خطای دریافت: ' + e.message; }
    finally { buttons.forEach(b => b.disabled = false); }
}
document.getElementById('codal-local').onclick = () => loadCodal(false);
document.getElementById('codal-sync').onclick = () => loadCodal(true);
const codalSymbol = new URLSearchParams(location.search).get('symbol');
if(codalSymbol) document.getElementById('codal-symbol').value = codalSymbol;
loadCodal(false);
