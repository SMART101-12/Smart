"""Minimal default dashboard; advanced tools remain under /legacy."""

HTML = '''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SMART</title>
<style>body{font:16px Tahoma,Arial;background:#f2f5fa;color:#183049;max-width:850px;margin:40px auto;padding:16px}
main,section{background:white;border-radius:14px;padding:22px;margin:16px 0;box-shadow:0 3px 16px #1232}
input,button{font:inherit;padding:12px;border-radius:8px}input{width:min(90%,440px);border:1px solid #abb}
button{border:0;background:#17659a;color:white;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}
a{color:#17659a}li{padding:3px}table{width:100%;border-collapse:collapse}th,td{text-align:right;border-bottom:1px solid #e1e7ee;padding:9px;vertical-align:top}td small{display:block;color:#5b6876}.model-wrap{overflow-x:auto}</style></head><body><main><h1>SMART</h1>
<label for="symbol">نماد</label><br><input id="symbol" placeholder="پالایش" autocomplete="off">
<button id="analyze">تحلیل سهم</button></main>
<section><h2>وضعیت تحلیل</h2><p id="status">نماد را وارد کنید.</p><ol id="stages"></ol></section>
<section><h2>نتیجه تحلیل</h2><div id="result"></div></section>
<section><h2>لایه‌های تحلیل جامع</h2><div id="analysis-layers">پس از تحلیل، بازار، صنعت، تکنیکال، بنیادی، جریان پول، setup، بک‌تست و ریسک اینجا نمایش داده می‌شوند.</div></section>
<section><h2>۱۰ روش مستقل تحلیل بازار</h2><div id="market-models">پس از تحلیل نماد، دیدگاه هر روش اینجا نمایش داده می‌شود.</div></section>
<p><a href="/legacy">ابزارهای پیشرفته و گزارش‌های قبلی</a></p>
<script>
const status=document.getElementById('status'),stages=document.getElementById('stages'),result=document.getElementById('result'),modelBox=document.getElementById('market-models');
const signalNames={bullish:'صعودی',bearish:'نزولی',neutral:'خنثی',unavailable:'داده ناکافی'};
const decisionNames={BUY:'خرید مشروط به گیت‌های تأییدشده',WATCH:'زیر نظر',WAIT:'انتظار',NO_SETUP:'الگوی ورود معتبر موجود نیست',INVALIDATED:'الگو باطل شده',AVOID:'پرهیز'};
const gateNames={data_quality:'کیفیت داده',adjustment_history:'سابقه تعدیل قیمت',market_context:'وضعیت بازار',industry_context:'وضعیت صنعت',context_source_verification:'تأیید منبع شاخص‌ها',technical_alignment:'هم‌جهتی تکنیکال',setup_confirmation:'تأیید الگوی ورود',validation:'اعتبارسنجی مدل',individual_flow:'ورود پول حقیقی',volume_confirmation:'تأیید حجم',financial_publication:'انتشار معتبر کدال',fundamental_completeness:'کفایت بنیادی',risk_constraints:'ریسک و نقدشوندگی',complete_evidence:'کامل بودن شواهد'};
function renderLayers(data){const box=document.getElementById('analysis-layers');box.replaceChildren();
const labels={market:'بازار',industry:'صنعت',technical:'تکنیکال چندبازه‌ای',fundamental:'بنیادی و کدال',flow:'حجم و جریان پول',setup:'الگوی ورود و سطوح شرطی',backtest:'بک‌تست و اعتبارسنجی',risk:'ریسک'};
for(const [key,label] of Object.entries(labels)){const layer=data.layers?.[key]||{},panel=document.createElement('details'),title=document.createElement('summary');title.textContent=label+' — '+(layer.status||'ناموجود')+' | '+(layer.as_of||'تاریخ ناموجود');panel.append(title);
const note=document.createElement('p');let lines=[];
if(key==='market'||key==='industry'){const v=data[key]||{};lines=['وضعیت: '+(v.regime||'UNKNOWN'),'منبع: '+(v.source||'ناموجود'),'تعارض‌ها: '+(v.conflicts||[]).join('، ')]}
if(key==='technical'){const v=data.technical_structure||{};lines=['امتیاز توصیفی: '+(v.score_0_100??'ناموجود')+' از ۱۰۰؛ این عدد تصمیم خرید نیست',...Object.entries(v.timeframes||{}).map(([tf,x])=>tf+': '+x.status+' | روند '+(x.trend||'-')+' | آخرین کندل کامل '+(x.last_completed||'-'))]}
if(key==='fundamental'){const v=data.fundamental||{};lines=['نوع: '+(data.instrument_type||'-'),'امتیاز شرکت: '+(v.financial_score??'ناموجود'),'NAV هر واحد: '+(v.net_asset_value_per_unit?.value??'ناموجود'),'وضعیت منبع کدال: '+(data.fundamental_quality_gate?.source_status||'ناموجود')]}
if(key==='flow'){const v=data.flow||{};lines=['جریان واقعی: '+(v.observed_client_type?.signal||'UNAVAILABLE'),'خالص حجم حقیقی: '+(v.observed_client_type?.net_individual_volume??'ناموجود'),'نسبت حجم ۲۰ جلسه: '+(v.price_volume_proxy?.volume_ratio_20??'ناموجود'),'تعارض‌ها: '+(v.conflicts||[]).join('، ')]}
if(key==='setup'){const v=data.setup||{};lines=['وضعیت: '+(v.state||'ناموجود'),'سطوح: '+(v.confirmed_plan?'تأییدشده':'فرضی و مشروط'),'ورود: '+(v.entry??'-'),'حد ضرر: '+(v.stop??'-'),'هدف اول / دوم: '+(v.target_1??'-')+' / '+(v.target_2??'-'),'اعتبار تا: '+(v.expires_on||'-')]}
if(key==='backtest'){const v=data.backtest?.audit||{};lines=['تصمیم اعتبارسنجی: '+(data.self_test?.decision||'ناموجود'),'validation: '+(v.validation_passed??'ناموجود'),'frozen test: '+(v.frozen_test_passed??'ناموجود'),'گیت‌های ردشده: '+(v.failed_checks||[]).join('، ')]}
if(key==='risk'){const v=data.setup||{};lines=['ریسک: '+(v.risk||'ناموجود'),'فاصله حد ضرر: '+(v.risk_pct??'-')+'٪','نسبت سود/زیان: '+(v.reward_risk_1??'-'),'نقدشوندگی: '+(v.liquidity||'ناموجود'),'ریسک گپ: '+(v.gap_execution_risk||'ناموجود')]}
note.textContent=lines.join(' | ');panel.append(note);if(layer.errors?.length){const errors=document.createElement('p');errors.textContent='داده/گیت ناقص: '+layer.errors.join('، ');panel.append(errors)}const raw=document.createElement('pre');raw.textContent=JSON.stringify(layer.evidence||{},null,2);panel.append(raw);box.append(panel)}}
function renderModels(report){modelBox.replaceChildren();if(!report?.models?.length){modelBox.textContent='داده‌ای برای این روش‌ها موجود نیست.';return}
const summary=document.createElement('p');summary.textContent='تاریخ داده: '+(report.as_of||'-')+' | صعودی: '+(report.counts?.bullish??0)+' | نزولی: '+(report.counts?.bearish??0)+' | خنثی: '+(report.counts?.neutral??0)+' | داده ناکافی: '+(report.counts?.unavailable??0);modelBox.append(summary);
const wrap=document.createElement('div'),table=document.createElement('table'),head=document.createElement('thead'),body=document.createElement('tbody');wrap.className='model-wrap';
const hrow=document.createElement('tr');for(const label of ['روش','نتیجه','معیار و دادهٔ محاسبه‌شده']){const th=document.createElement('th');th.textContent=label;hrow.append(th)}head.append(hrow);
for(const m of report.models){const tr=document.createElement('tr');const title=document.createElement('td');title.textContent=m.title;const signal=document.createElement('td');signal.textContent=signalNames[m.signal]||m.signal;const detail=document.createElement('td');detail.textContent=m.reason||'-';if(Object.keys(m.metrics||{}).length){const small=document.createElement('small');small.textContent=JSON.stringify(m.metrics);detail.append(small)}tr.append(title,signal,detail);body.append(tr)}table.append(head,body);wrap.append(table);modelBox.append(wrap);
const notice=document.createElement('p');notice.textContent=report.interpretation||'این روش‌ها سیگنال اجرایی نیستند.';modelBox.append(notice)}
function show(job){status.textContent=job.status+' — '+job.stage+(job.warnings?.length?' — هشدار: '+job.warnings.map(x=>x.stage+': '+x.error).join('؛ '):'');
stages.replaceChildren(...(job.stages||[]).map(x=>{const li=document.createElement('li');li.textContent=x.name+' — '+x.status+' ('+x.seconds+'s)';return li}));}
document.getElementById('analyze').onclick=async()=>{const symbol=document.getElementById('symbol').value.trim();if(!symbol)return;
status.textContent='در حال شروع...';result.replaceChildren();document.getElementById('analysis-layers').replaceChildren();modelBox.textContent='در حال محاسبهٔ روش‌ها...';try{let r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})});
let job=await r.json();if(!r.ok)throw Error(JSON.stringify(job.detail));show(job);
for(let i=0;i<300;i++){await new Promise(resolve=>setTimeout(resolve,1000));r=await fetch('/api/analyze/'+encodeURIComponent(job.analysis_id));job=await r.json();show(job);
if(!['QUEUED','RUNNING'].includes(job.status))break}
if(['COMPLETED','PARTIAL'].includes(job.status)){r=await fetch('/api/analysis/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(job.analysis_id));
const data=await r.json();renderModels(data.market_models);renderLayers(data);const headline=document.createElement('p');headline.textContent='تصمیم: '+(decisionNames[data.decision?.state]||data.decision?.state||'گزارش قدیمی')+' | نوع: '+(data.instrument_type||'-')+' | ارزیابی مدل: '+(data.self_test?.decision||'ناموجود')+' | وضعیت: '+data.status;result.append(headline);
if(data.decision){const gates=document.createElement('p');gates.textContent='گیت‌های تأییدنشده: '+(data.decision.failed_gates||[]).map(x=>gateNames[x]||x).join('، ');result.append(gates);const confidence=document.createElement('p');confidence.textContent='اطمینان در شواهد تحلیلی: '+(data.confidence_evidence?.score_0_100??'ناموجود')+' از ۱۰۰؛ کالیبره نشده و احتمال سود نیست. امتیاز شواهد: '+(data.decision.weighted_evidence_score??'به علت داده ناقص محاسبه نمی‌شود');result.append(confidence)}
const setup=data.entry_exit||{};const note=document.createElement('p');note.textContent='ورود/خروج: '+(setup.signal_status||'ناموجود')+' — '+(setup.reason||'داده کافی نیست');result.append(note);
if(setup.conditional){const c=setup.conditional,zone=c.entry_zone_if_confirmed||c.entry_zone||[];const levels=document.createElement('pre');levels.textContent=['سناریوی شرطی، نه دستور معامله:','ورود: '+zone.join(' تا '),'حد ضرر: '+(c.stop_if_entered??c.sl??'-'),'هدف اول: '+(c.target_1_if_entered??c.tp1??'-'),'هدف دوم: '+(c.target_2_if_entered??c.tp2??'-'),'شرط/ابطال: '+(c.confirmation??c.invalidation_condition??'-')+' / '+(c.invalidation??'-')].join(String.fromCharCode(10));result.append(levels)}
const p=document.createElement('details');const title=document.createElement('summary');title.textContent='جزئیات کامل و منابع';const raw=document.createElement('pre');raw.textContent=JSON.stringify(data,null,2);p.append(title,raw);result.append(p);
const link=document.createElement('a');link.href='/api/analysis/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(job.analysis_id)+'/chatgpt';link.textContent='بستهٔ زمینه برای ChatGPT';result.prepend(link)}
}catch(e){status.textContent='خطا: '+e.message}};
</script></body></html>'''
