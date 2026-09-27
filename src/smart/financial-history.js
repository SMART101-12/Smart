/* All displayed values are repository facts or explicitly attributed calculations. */
const financialCharts = new Map();
const financialEscape = v => String(v ?? 'N/A').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const financialValue = v => v === null || v === undefined ? 'N/A' :
  Number(v).toLocaleString('fa-IR', {maximumFractionDigits: 4});

async function loadFinancial(symbol, target) {
  const box = document.getElementById(target);
  box.textContent = 'در حال بررسی داده محلی و گزارش‌های جدید کدال…';
  try {
    const response = await fetch('/api/financial-history?symbol=' + encodeURIComponent(symbol));
    const data = await response.json();
    if (!response.ok) throw Error(data.detail || 'دریافت ناموفق');
    renderFinancial(data, target);
  } catch (error) {
    box.textContent = 'داده مالی دریافت نشد: ' + error.message;
  }
}

function financialReferences(reference) {
  const refs = (Array.isArray(reference) ? reference : [reference]).filter(Boolean);
  return refs.map(ref => {
    let safe = false;
    try { const u = new URL(ref.url); safe = u.protocol === 'https:' &&
      ['codal.ir', 'www.codal.ir'].includes(u.hostname); } catch (_) { /* no link */ }
    const label = financialEscape(ref.document_id);
    return safe ? `<a href="${financialEscape(ref.url)}" target="_blank" rel="noopener noreferrer">${label}</a>` : label;
  }).join('، ');
}

function renderFinancial(data, target) {
  (financialCharts.get(target) || []).forEach(chart => chart.destroy());
  const localCharts = [];
  financialCharts.set(target, localCharts);
  const box = document.getElementById(target), e = financialEscape;
  const rows = data.annual, metrics = ['revenue','net_profit','operating_profit','eps',
    'operating_cash_flow','roe','liabilities','equity'];
  if (!rows.length) {
    box.innerHTML = `<section class="card" dir="rtl"><h2>تحلیل مالی ۵ ساله — ${e(data.symbol)}</h2>
      <div class="metric">امتیاز مالی: N/A</div><div class="metric">کیفیت داده: ${financialValue(data.data_quality_score)} / ۱۰۰</div>
      <div class="metric">پوشش: ۰ / ${e(data.coverage.required)}</div>
      <h3>داده معتبر کافی نیست</h3><p>اطلاعات این شاخص برای دوره موردنظر در داده‌های دریافت‌شده از کدال موجود نیست.</p>
      ${data.warnings.map(w=>`<p class="error">${e(w)}</p>`).join('')}
      <p class="muted">منبع مورد انتظار: کدال | آخرین همگام‌سازی موفق: ${e(data.freshness.last_sync_date)}</p>
      <a href="/api/financial-history/audit?symbol=${encodeURIComponent(data.symbol)}" target="_blank" rel="noopener">سوابق دریافت و خطاهای منبع</a></section>`;
    return;
  }
  box.innerHTML = `<section class="card" dir="rtl">
    <h2>تحلیل مالی ۵ ساله — ${e(data.symbol)}</h2>
    <p>مبنای گزارش: ${data.basis === 'standalone' ? 'شرکت اصلی' : 'تلفیقی'}</p>
    <div class="metric">امتیاز مالی: ${financialValue(data.financial_score)} / ۱۰۰</div>
    <div class="metric">کیفیت داده: ${financialValue(data.data_quality_score)} / ۱۰۰</div>
    <div class="metric">پوشش: ${e(data.coverage.available)} / ${e(data.coverage.required)}</div>
    <p>${e(data.status)} | منبع: KODAL | آخرین همگام‌سازی موفق: ${e(data.freshness.last_sync_date)}</p>
    ${data.warnings.map(w => `<p class="error">${e(w)}</p>`).join('')}
    ${!rows.length ? '<p>Insufficient verified data — اطلاعات معتبر کدال موجود نیست.</p>' : ''}
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">
    ${metrics.map((m,i) => `<div><h3>${e(data.labels[m])}</h3>
      <p class="muted">${e(rows.find(r=>r.cells[m].unit)?.cells[m].unit)} | KODAL | پوشش ${rows.filter(r=>r.cells[m].value!==null).length}/${data.coverage.required}<br>آخرین دریافت: ${e(data.freshness.last_sync_date)}</p>
      <div class="chart-wrap"><canvas id="${target}-chart-${i}" aria-label="${e(data.labels[m])}"></canvas></div></div>`).join('')}
    </div>
    <h3>5-Year Financial Tube</h3><p class="muted">مقادیر منفی در سمت منفی محور و داده گمشده به صورت N/A نمایش داده می‌شوند.</p>
    <div class="chart-wrap"><canvas id="${target}-tube"></canvas></div>
    <div style="overflow-x:auto"><table><thead><tr><th>شاخص / واحد / منبع</th>
      ${rows.map(r=>`<th>${e(r.period || r.year)}${r.restated ? ' (اصلاحی)' : ''}</th>`).join('')}</tr></thead>
      <tbody>${Object.keys(data.labels).map(m=>`<tr><th>${e(data.labels[m])}</th>${rows.map(r=> {
        const c = r.cells[m]; return `<td>${financialValue(c.value)}<br><small>${e(c.unit)}<br>${e(c.badge)}<br>${financialReferences(c.source_reference)}</small></td>`;
      }).join('')}</tr>`).join('')}</tbody></table></div>
    <details><summary>قواعد و اجزای امتیازدهی</summary>${Object.entries(data.components).map(([name,c]) =>
      `<h4>${e(name)}: ${financialValue(c.score)} — وزن ${e(c.weight)}</h4>${c.metrics.map(m=>
        `<p>${e(data.labels[m.metric])}: ${financialValue(m.score)} — ${e(m.rule)}</p>`).join('')}`).join('')}</details>
    <h3>تحلیل مالی هوشمند</h3>${data.persian_analysis.facts.map(f=>
      `<p><b>${e(f.title)}:</b> ${e(f.text)}</p>`).join('')}
    <p>نقاط قوت: ${e(data.persian_analysis.strengths.join('، ') || 'N/A')}</p>
    <p>نقاط ضعف: ${e(data.persian_analysis.weaknesses.join('، ') || 'N/A')}</p>
    <p>${e(data.persian_analysis.conclusion)}</p>
    <a href="/api/financial-history/audit?symbol=${encodeURIComponent(data.symbol)}" target="_blank" rel="noopener">سوابق دریافت و نسخه‌های گزارش</a>
  </section>`;
  if (!window.Chart || !rows.length) return;
  const labels = rows.map(r=>r.period || String(r.year));
  metrics.forEach((metric,i) => {
    // Mixed units are shown in the table, never plotted on one numerical scale.
    const units = new Set(rows.filter(r=>r.cells[metric].value!==null).map(r=>r.cells[metric].unit));
    if (units.size > 1) return;
    localCharts.push(new Chart(document.getElementById(`${target}-chart-${i}`), {
      type:'line', data:{labels, datasets:[{label:data.labels[metric],
        data:rows.map(r=>r.cells[metric].value), borderColor:'#2563eb',
        spanGaps:false, tension:0, pointRadius:4}]},
      options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}}
    }));
  });
  const revenueUnits = new Set(rows.filter(r=>r.cells.revenue.value!==null).map(r=>r.cells.revenue.unit));
  if (revenueUnits.size <= 1) localCharts.push(new Chart(document.getElementById(`${target}-tube`), {
    type:'bar', data:{labels, datasets:[{label:data.labels.revenue,
      data:rows.map(r=>r.cells.revenue.value), backgroundColor:'#0f766e', borderRadius:10}]},
    options:{indexAxis:'y', responsive:true, maintainAspectRatio:false, scales:{x:{beginAtZero:true}}}
  }));
}
