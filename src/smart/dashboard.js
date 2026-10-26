'use strict';
const $=id=>document.getElementById(id);
const numberFormat=new Intl.NumberFormat('fa-IR',{maximumFractionDigits:0});
const fmt=v=>v==null?'—':typeof v==='number'?(Number.isFinite(v)?numberFormat.format(v):'—'):String(v);
const dateFmt=v=>{if(!v)return '—';v=String(v);if(/^\d{8}$/.test(v))v=v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6);const d=new Date(v+'T12:00:00');return Number.isNaN(d.getTime())?v:new Intl.DateTimeFormat('fa-IR').format(d)};
const names={BUY:'خرید با شروط تأییدشده',WATCH:'زیر نظر',WAIT:'انتظار برای تأیید',NO_SETUP:'الگوی ورود معتبر موجود نیست',INVALIDATED:'الگو باطل شده',AVOID:'پرهیز',COMPLETED:'تکمیل شده',PARTIAL:'داده ناقص',RUNNING:'در حال پردازش',QUEUED:'در صف',FAILED:'ناموفق',SUCCESS:'موفق',UNAVAILABLE:'ناموجود',UNKNOWN:'نامشخص',DEGRADED:'داده ناقص',BULL:'صعودی',BEAR:'نزولی',NEUTRAL:'خنثی',FUND:'صندوق',EQUITY:'سهام',bullish:'صعودی',bearish:'نزولی',neutral:'خنثی',unavailable:'داده ناکافی',daily:'روزانه',weekly:'هفتگی',monthly:'ماهانه',medium:'متوسط',high:'زیاد',low:'کم'};
Object.assign(names,{HOLD:'نیازمند شواهد بیشتر',REJECT:'رد شده',APPROVE:'تأیید شده',UNVERIFIED:'تأیید نشده',MEDIUM:'متوسط',HIGH:'زیاد',LOW:'کم',SETUP_FORMING:'الگو در حال شکل‌گیری',CONFIRMED:'تأیید شده',READY:'آماده',COMPLETE:'کامل',PASS:'قبول',FAIL:'رد',historical_data:'تاریخچه قیمت',data_quality_gate:'کیفیت داده',codal_sync:'دریافت کدال',symbol_search:'شناسایی نماد',market_analysis:'تحلیل بازار',historical_exam:'آزمون تاریخی',fundamental_quality_gate:'کیفیت بنیادی',technical_structure:'ساختار تکنیکال',market_context:'وضعیت بازار',industry_context:'وضعیت صنعت',finalize:'جمع‌بندی',done:'پایان'});
const label=v=>names[v]||fmt(v);
names.EXPIRED='فرصت ورود منقضی شده';
const gateNames={data_quality:'کیفیت داده',adjustment_history:'سابقه تعدیل قیمت',market_context:'وضعیت بازار',industry_context:'وضعیت صنعت',context_source_verification:'تأیید منبع شاخص‌ها',technical_alignment:'هم‌جهتی تکنیکال',setup_confirmation:'تأیید الگوی ورود',validation:'اعتبارسنجی مدل',approved_model_version:'نسخه تأییدشده مدل',individual_flow:'ورود پول حقیقی',volume_confirmation:'تأیید حجم',financial_publication:'انتشار معتبر کدال',fundamental_completeness:'کفایت بنیادی',risk_constraints:'ریسک و نقدشوندگی',complete_evidence:'کامل بودن شواهد'};
function displayText(value){return String(value).replace(/(?<![\w.-])(-?\d+\.\d+)(?![\w.])/g,(_,n)=>'≈ '+fmt(Number(n)))}
gateNames.entry_validity='اعتبار زمانی ورود';gateNames.net_reward_risk='بازده به ریسک پس از هزینه';
function el(tag,text,cls){const node=document.createElement(tag);if(text!=null)node.textContent=displayText(text);if(cls)node.className=cls;return node}
function roundedJSON(value){return JSON.stringify(value,(_,v)=>typeof v==='number'?Math.round(v):v,2)}
function detail(title,value){const d=el('details',null,'evidence');d.append(el('summary',title),el('pre',roundedJSON(value)));return d}
function kpi(title,value,cls=''){const node=el('div',null,'kpi '+cls);node.append(el('span',title),el('strong',value));return node}
function renderLayers(data){const box=$('analysis-layers');box.classList.remove('empty');box.replaceChildren();const titles={market:'بازار',industry:'صنعت',technical:'تکنیکال چندبازه‌ای',fundamental:'بنیادی و کدال',flow:'حجم و جریان پول',setup:'الگوی ورود',backtest:'اعتبارسنجی',risk:'ریسک'};
for(const [key,title] of Object.entries(titles)){const layer=data.layers?.[key]||{},d=el('details',null,'layer'),s=el('summary',title);s.append(el('span',label(layer.status)));d.append(s);let lines=[];
if(['market','industry'].includes(key)){const v=data[key]||{};lines=['روند: '+label(v.regime),'منبع: '+fmt(v.source)]}
if(key==='technical'){const v=data.technical_structure||{};lines=['امتیاز توصیفی: '+fmt(v.score_0_100)+' از ۱۰۰',...Object.entries(v.timeframes||{}).map(([tf,x])=>label(tf)+' · '+label(x.trend)+' · '+dateFmt(x.last_completed))]}
if(key==='fundamental'){const v=data.fundamental||{};lines=['نوع دارایی: '+label(data.instrument_type),'امتیاز شرکت: '+fmt(v.financial_score),'NAV هر واحد: '+fmt(v.net_asset_value_per_unit?.value),'منبع کدال: '+label(data.fundamental_quality_gate?.source_status)]}
if(key==='flow'){const v=data.flow||{};lines=['جریان واقعی: '+label(v.observed_client_type?.signal),'خالص حجم حقیقی: '+fmt(v.observed_client_type?.net_individual_volume),'نسبت حجم ۲۰ جلسه: '+fmt(v.price_volume_proxy?.volume_ratio_20)]}
if(key==='setup'){const v=data.setup||{};lines=['وضعیت: '+label(v.state),'سطوح: '+(v.confirmed_plan?'تأییدشده':'فرضی و مشروط'),'اعتبار تا: '+dateFmt(v.expires_on)]}
if(key==='backtest'){const v=data.backtest?.audit||{};lines=['ارزیابی مدل: '+label(data.self_test?.decision),'اعتبارسنجی: '+(v.validation_passed===true?'قبول':v.validation_passed===false?'رد':'ناموجود'),'آزمون نهایی: '+(v.frozen_test_passed===true?'قبول':v.frozen_test_passed===false?'رد':'ناموجود')]}
if(key==='risk'){const v=data.setup||{};lines=['ریسک: '+label(v.risk),'فاصله حد ضرر: '+fmt(v.risk_pct)+'٪','نسبت سود به زیان (گردشده): '+fmt(v.reward_risk_1),'نقدشوندگی: '+label(v.liquidity)]}
for(const line of lines)d.append(el('p',line));if(layer.errors?.length)d.append(el('p','داده / شروط ناقص: '+layer.errors.join('، '),'notice'));d.append(el('p','تاریخ شواهد: '+dateFmt(layer.as_of),'muted'),detail('شواهد فنی · اعداد گردشده',layer.evidence||{}));box.append(d)}}
function renderModels(report){const box=$('market-models');box.classList.remove('empty');box.replaceChildren();if(!report?.models?.length){box.append(el('p','داده‌ای برای این روش‌ها موجود نیست.'));return}const counts=el('div',null,'chips');for(const key of ['bullish','bearish','neutral','unavailable'])counts.append(el('span',label(key)+' '+fmt(report.counts?.[key]??0),'chip '+key));box.append(counts);const wrap=el('div',null,'model-wrap'),table=el('table'),head=el('thead'),hr=el('tr'),body=el('tbody');for(const title of ['روش تحلیل','دیدگاه','معیار و شواهد'])hr.append(el('th',title));head.append(hr);
for(const m of report.models){const tr=el('tr'),signal=el('td'),info=el('td',m.reason||'—');signal.append(el('span',label(m.signal),'chip '+(['bullish','bearish','neutral'].includes(m.signal)?m.signal:'unavailable')));if(Object.keys(m.metrics||{}).length)info.append(detail('معیارها · بدون اعشار',m.metrics));tr.append(el('td',m.title),signal,info);body.append(tr)}table.append(head,body);wrap.append(table);box.append(wrap,el('p',report.interpretation||'این روش‌ها به‌تنهایی سیگنال اجرایی نیستند.','muted'))}
function reportScenario(data){const c=data.entry_exit?.conditional,confirmed=data.setup?.confirmed_plan,candidate=confirmed||c;const valid=data.entry_exit?.engine_version==='STRUCTURAL-ENTRY-1'&&candidate?.target_method==='observed_pivot_resistance'&&candidate?.level_evidence?.target_1&&candidate?.level_evidence?.target_2;return {c:valid?c:null,confirmed:Boolean(valid&&confirmed),plan:valid?(confirmed?data.setup:c):null,legacy:Boolean(candidate)&&!valid}}
function renderLevelEvidence(box,data){const evidence=data.entry_exit?.evidence,levels=evidence?.structural_levels;if(!levels)return;const section=el('details',null,'evidence');section.append(el('summary','????? ????? ???? ???? ? ????'));section.append(el('p','???? ?? ????? ????? ???? ? ??? ????? ??????? ????? ?? ?????????? ?????????? ?????? ???????. ???? ??? ?? ???? ??? ????? ????? ??? ? ??? ???? ????????.'));for(const [key,title] of [['supports','?????'],['resistances','??????']]){const values=levels[key]||[];section.append(el('p',title+': '+(values.length?values.slice(0,3).map(v=>fmt(v.price)+' ? '+(v.pivot_dates||[]).map(dateFmt).join('? ')).join(' / '):'???? ???????? ????? ????')))}const checks=evidence.confirmation;if(checks)section.append(el('p','????? ????: '+(checks.breakout?'???':'???')+' ? ?????????: '+(checks.retest?'???':'???')+' ? ????? ????: '+(checks.trend_pullback?'???':'???')+' ? ???: '+(checks.volume?'???':'???')));box.append(section)}
function renderReport(data,symbol,id){const box=$('result');box.classList.remove('empty');box.replaceChildren();$('report-date').textContent='تاریخ داده: '+dateFmt(data.as_of);const hero=el('div',null,'decision-hero');hero.append(el('h3',symbol+' · '+label(data.decision?.state||'UNKNOWN')),el('p',label(data.instrument_type)+' · '+label(data.status)+' · ارزیابی مدل: '+label(data.self_test?.decision)));box.append(hero);
if(data.codal_sync?.action_required){const help=el('a','\u0628\u0631\u0627\u06cc \u0627\u062f\u0627\u0645\u0647 \u062f\u0631\u06cc\u0627\u0641\u062a \u06a9\u062f\u0627\u0644\u060c \u062a\u0623\u06cc\u06cc\u062f \u0634\u0645\u0627 \u0644\u0627\u0632\u0645 \u0627\u0633\u062a');help.href='/financial-reports?symbol='+encodeURIComponent(symbol);box.append(help)}
const {c,confirmed,plan,legacy}=reportScenario(data);if(legacy)box.append(el('p','???? ??? ????? ?? ??? ????? ?????? ???????? ???? ???? ????? ?? ?????? ????? ????? ???? ??????.','notice'));renderLevelEvidence(box,data);box.append(el('p',confirmed?'سطوح تأییدشده':c?'سناریوی مشروط؛ اجرای آن به تأیید شروط تحلیل وابسته است.':'سطوح ورود و خروج معتبر در دسترس نیست.','notice'));const grid=el('div',null,'kpi-grid'),zone=c?.entry_zone_if_confirmed||c?.entry_zone||[];grid.append(kpi('محدوده ورود · ریال',confirmed?fmt(plan.entry):zone.length?zone.map(fmt).join(' تا '):'—'),kpi('حد ضرر · ریال',fmt(confirmed?plan.stop:c?.stop_if_entered??c?.sl),'stop'),kpi('هدف اول · ریال',fmt(confirmed?plan.target_1:c?.target_1_if_entered??c?.tp1),'target'),kpi('هدف دوم · ریال',fmt(confirmed?plan.target_2:c?.target_2_if_entered??c?.tp2),'target'));box.append(grid);
if(data.entry_exit?.reason)box.append(el('p',data.entry_exit.reason,'muted'));if(c)box.append(el('p','شرط تأیید / ابطال: '+(c.confirmation??c.invalidation_condition??'—')+' / '+(c.invalidation??'—'),'muted'));
const rules=data.risk?.exit_rules;if(rules){const exit=el('details',null,'evidence');exit.append(el('summary','برنامه خروج و هزینه معامله'),el('p','اعتبار ورود تا: '+dateFmt(data.setup?.expires_on)),el('p','حد ضرر با لمس قیمت فعال می‌شود؛ در گپ یا صف، خروج در قیمت حد ضرر تضمین نیست.'),el('p','هدف اول: بررسی خروج بخشی؛ هدف دوم: بررسی خروج باقیمانده. لمس هدف به معنی فروش انجام‌شده نیست.'),el('p','پس از تأیید فروش هدف اول، حد ضرر جدید از جلسه بعد اعمال می‌شود.'),el('p','خروج زمانی: پس از '+fmt(rules.time_exit_sessions)+' جلسه، ارزیابی خروج در اولین فرصت بعدی.'),detail('فرض هزینه و قواعد دقیق',rules));box.append(exit)}
const gates=el('div',null,'chips');for(const key of data.decision?.failed_gates||[])gates.append(el('span',gateNames[key]||key,'chip warning'));if(gates.childNodes.length){box.append(el('p','شروط تأییدنشده:'),gates)}box.append(el('p','امتیاز شواهد: '+fmt(data.decision?.weighted_evidence_score)+' · اطمینان شواهد: '+fmt(data.confidence_evidence?.score_0_100)+' از ۱۰۰؛ این اعداد احتمال سود نیستند.','muted'));const links=el('div',null,'links'),base='/api/analysis/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(id);for(const [suffix,title] of [['','گزارش JSON با دقت اصلی'],['/chatgpt','بسته زمینه ChatGPT']]){const a=el('a',title);a.href=base+suffix;a.target='_blank';a.rel='noopener';links.append(a)}box.append(links);renderLayers(data);renderModels(data.market_models)}

// Window uses observed session indices; missing sessions are never synthesized.
function chartWindow(total,start,size){size=Math.min(total,Math.max(Math.min(5,total),Math.round(size)));start=Math.max(0,Math.min(total-size,Math.round(start)));return {start,size}}
class PriceChart{
constructor(){this.canvas=$('price-chart');this.ctx=this.canvas.getContext('2d');this.bars=[];this.start=0;this.size=90;this.hover=null;this.drag=null;this.mode='line';this.levels=[];this.showLevels=false;new ResizeObserver(()=>this.draw()).observe(this.canvas.parentElement);
this.canvas.addEventListener('wheel',e=>{if(!this.bars.length)return;e.preventDefault();this.zoom(e.deltaY>0?1.25:.8,this.fraction(e.clientX))},{passive:false});
this.canvas.addEventListener('pointerdown',e=>{if(e.pointerType==='touch'||!this.bars.length)return;this.drag={x:e.clientX,start:this.start};this.canvas.setPointerCapture(e.pointerId)});
this.canvas.addEventListener('pointermove',e=>{if(this.drag){this.setWindow(this.drag.start-(e.clientX-this.drag.x)/this.plotWidth*this.size,this.size)}else this.hover=Math.round(this.start+this.fraction(e.clientX)*(this.size-1));this.draw()});
for(const event of ['pointerup','pointercancel','lostpointercapture'])this.canvas.addEventListener(event,()=>{this.drag=null});this.canvas.addEventListener('pointerleave',()=>{this.hover=null;this.draw()});this.canvas.addEventListener('dblclick',()=>this.range(90));this.canvas.addEventListener('keydown',e=>{if(['+','=','-','ArrowLeft','ArrowRight','Home'].includes(e.key)){e.preventDefault();if(e.key==='Home')this.range(90);else if(e.key.startsWith('Arrow'))this.setWindow(this.start+(e.key==='ArrowLeft'?-1:1)*Math.max(1,this.size/5),this.size);else this.zoom(e.key==='-'?1.25:.8)}});
document.querySelectorAll('[data-range]').forEach(b=>b.onclick=()=>this.range(b.dataset.range));$('zoom-in').onclick=()=>this.zoom(.8);$('zoom-out').onclick=()=>this.zoom(1.25);$('chart-reset').onclick=()=>this.range(90);
$('chart-mode').onclick=()=>{this.mode=this.mode==='line'?'candle':'line';$('chart-mode').textContent=this.mode==='line'?'نمای کندلی':'نمای خطی';this.draw()};
$('chart-levels').onclick=()=>{this.showLevels=!this.showLevels;$('chart-levels').setAttribute('aria-pressed',String(this.showLevels));$('chart-levels').textContent=this.showLevels?'پنهان کردن سطوح':'نمایش سطوح گزارش';this.draw()}}
setScenario(data){const {confirmed,plan}=reportScenario(data),s=plan||{},zone=s.entry_zone_if_confirmed||s.entry_zone||[];this.levels=[['ورود',confirmed?s.entry:zone[zone.length-1],'#b57b20'],['حد ضرر',confirmed?s.stop:s.stop_if_entered??s.sl,'#b84652'],['هدف اول',confirmed?s.target_1:s.target_1_if_entered??s.tp1,'#087f8c'],['هدف دوم',confirmed?s.target_2:s.target_2_if_entered??s.tp2,'#087f8c']].filter(x=>typeof x[1]==='number'&&Number.isFinite(x[1])&&x[1]>0).map(x=>[x[0]+(confirmed?' · تأییدشده':' · مشروط'),x[1],x[2]]);this.draw()}
fraction(x){const r=this.canvas.getBoundingClientRect();return Math.max(0,Math.min(1,(x-r.left-16)/(this.plotWidth||1)))}
setWindow(start,size){Object.assign(this,chartWindow(this.bars.length,start,size));this.hover=null;document.querySelectorAll('[data-range]').forEach(b=>b.classList.remove('active'));this.draw()}
zoom(factor,anchor=.5){if(!this.bars.length)return;const next=chartWindow(this.bars.length,0,this.size*factor).size;this.setWindow(this.start+(this.size-next)*anchor,next)}
range(value){const size=value==='all'?this.bars.length:Number(value);this.setWindow(this.bars.length-size,size);document.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('active',String(value)===b.dataset.range))}
load(data){this.bars=data.bars||[];this.range(90);$('chart-empty').textContent=this.bars.length?'':'داده معتبر قیمت برای نمودار موجود نیست.';$('chart-tooltip').textContent='منبع: '+fmt(data.source)+' · آخرین جلسه: '+dateFmt(data.as_of)+' · تعدیل: '+(data.adjustment==='VERIFIED'?'تأییدشده':'تأیید نشده')}
clear(message='در حال بارگذاری نمودار…'){this.bars=[];this.levels=[];this.hover=null;this.draw();$('chart-empty').textContent=message;$('chart-tooltip').textContent=''}
draw(){const c=this.canvas,ctx=this.ctx,r=c.getBoundingClientRect(),w=r.width,h=r.height;if(!w||!h)return;const ratio=window.devicePixelRatio||1;if(c.width!==Math.round(w*ratio))c.width=Math.round(w*ratio);if(c.height!==Math.round(h*ratio))c.height=Math.round(h*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,w,h);if(!this.bars.length)return;this.plotWidth=Math.max(1,w-96);const left=16,right=left+this.plotWidth,top=22,bottom=h-95,rows=this.bars.slice(this.start,this.start+this.size);const values=this.mode==='candle'?rows.flatMap(b=>[b.low,b.high]):rows.map(b=>b.close);if(this.showLevels)values.push(...this.levels.map(x=>x[1]));const lo=Math.min(...values),hi=Math.max(...values),padding=Math.max((hi-lo)*.1,hi*.005,1),min=lo-padding,max=hi+padding;const x=i=>left+i/Math.max(1,rows.length-1)*this.plotWidth,y=v=>bottom-(v-min)/(max-min)*(bottom-top);ctx.font='11px Tahoma';ctx.textAlign='left';ctx.fillStyle='#64748b';ctx.strokeStyle='#e4eaf2';
for(let i=0;i<5;i++){const value=min+(max-min)*i/4,py=y(value);ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(right,py);ctx.stroke();ctx.fillText(fmt(value),right+8,py+4)}
if(this.mode==='line'){ctx.beginPath();rows.forEach((b,i)=>i?ctx.lineTo(x(i),y(b.close)):ctx.moveTo(x(i),y(b.close)));ctx.strokeStyle='#087f8c';ctx.lineWidth=2;ctx.stroke();ctx.lineWidth=1}
else{const width=Math.max(1,Math.min(12,this.plotWidth/rows.length*.6));rows.forEach((b,i)=>{ctx.fillStyle=ctx.strokeStyle=b.close>=b.open?'#087f8c':'#b84652';ctx.beginPath();ctx.moveTo(x(i),y(b.high));ctx.lineTo(x(i),y(b.low));ctx.stroke();ctx.fillRect(x(i)-width/2,Math.min(y(b.open),y(b.close)),width,Math.max(1,Math.abs(y(b.open)-y(b.close))))})}
if(this.showLevels)for(const [title,value,color] of this.levels){ctx.save();ctx.strokeStyle=ctx.fillStyle=color;ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(left,y(value));ctx.lineTo(right,y(value));ctx.stroke();ctx.setLineDash([]);ctx.textAlign='left';ctx.fillText(title+' · '+fmt(value),left+8,y(value)-5);ctx.restore()}
const vmax=Math.max(1,...rows.map(b=>b.volume));rows.forEach((b,i)=>{ctx.fillStyle=b.close>=b.open?'#93d4c6':'#edbbc2';ctx.fillRect(x(i)-1,h-38-b.volume/vmax*42,Math.max(1,Math.min(8,this.plotWidth/rows.length-1)),b.volume/vmax*42)});
ctx.fillStyle='#64748b';ctx.textAlign='center';for(const i of [...new Set([0,Math.floor((rows.length-1)/2),rows.length-1])]){ctx.textAlign=i===0?'left':i===rows.length-1?'right':'center';ctx.fillText(dateFmt(rows[i].source_date),x(i),h-12)}
if(this.hover!=null&&this.hover>=this.start&&this.hover<this.start+rows.length){const b=this.bars[this.hover],px=x(this.hover-this.start);ctx.strokeStyle='#91a9bc';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(px,top);ctx.lineTo(px,h-38);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#087f8c';ctx.beginPath();ctx.arc(px,y(b.close),4,0,Math.PI*2);ctx.fill();$('chart-tooltip').textContent=dateFmt(b.source_date)+' · پایانی: '+fmt(b.close)+' · باز: '+fmt(b.open)+' · بیشینه: '+fmt(b.high)+' · کمینه: '+fmt(b.low)+' · حجم: '+fmt(b.volume)}
}}
const chart=new PriceChart();
Object.assign(names,{RATE_LIMITED:'محدودیت درخواست',AVAILABLE:'داده قابل استفاده',INTEGRITY_ERROR:'خطای یکپارچگی گزارش',FRESH:'تازه',STALE:'قدیمی',UP:'صعودی',DOWN:'نزولی',MIXED:'ترکیبی'});
function observationText(value) {
    const titles={status:'کیفیت',latest:'آخرین جلسه',freshness:'تازگی',blockers:'موانع',market:'بازار',industry:'صنعت',risk:'ریسک',reward_risk_1:'سود به زیان (گردشده)',liquidity:'نقدشوندگی',gap_execution_risk:'اجرای گپ',percent_of_20_session_mean:'درصد میانگین حجم ۲۰ جلسه'};
    if(value==null)return 'ناموجود';
    if(Array.isArray(value))return value.length?value.map(label).join('، '):'بدون مانع';
    if(typeof value==='object')return Object.entries(value).map(([key,v])=>(titles[key]||key)+': '+observationText(v)).join(' · ');
    return label(value);
}
function renderInsights(data) {
    const health=$('source-health');health.classList.remove('empty');health.replaceChildren();
    for(const source of data.sources||[]) {
        const panel=el('div',null,'layer');panel.append(el('strong',source.source),el('span',label(source.status),'chip'),el('p','تاریخ داده: '+dateFmt(source.data_date),'muted'),el('p',source.description));
        if(source.errors?.length)panel.append(detail('محدودیت‌های ثبت‌شده',source.errors));health.append(panel);
    }
    if(data.codal_cooldown){const deadline=new Date(data.codal_cooldown.retry_at);health.append(el('p','کدال اکنون در وقفه درخواست است؛ تلاش بعدی از '+deadline.toLocaleString('fa-IR',{timeZone:'Asia/Tehran'})+' به وقت تهران.','notice'))}
    const failed=(data.gates||[]).filter(g=>g.passed===false),all=el('details',null,'evidence'),table=el('table'),head=el('thead'),hr=el('tr'),body=el('tbody'),wrap=el('div',null,'model-wrap');
    all.append(el('summary','چرا این تصمیم صادر شده؟ '+fmt(failed.length)+' شرط تأییدنشده · مشاهده مقدار و اقدام بعدی'));
    for(const title of ['شرط','وضعیت ثبت‌شده','شرط لازم / اقدام بعدی'])hr.append(el('th',title));head.append(hr);
    for(const g of data.gates||[]) {
        const tr=el('tr'),name=el('td',g.title),observed=el('td',observationText(g.observed)),action=el('td',g.required);
        name.append(el('p',g.passed===true?'تأیید شده':g.passed===false?'تأیید نشده':'ناموجود',g.passed?'badge':'chip warning'));
        if(!g.passed)action.append(el('p',g.next_step,'muted'));tr.append(name,observed,action);body.append(tr);
    }
    table.append(head,body);wrap.append(table);all.append(wrap);$('result').append(all);
}
function renderHistory(data) {
    const box=$('analysis-history');box.classList.remove('empty');box.replaceChildren();$('history-symbol').textContent=data.symbol||'';
    const items=data.items||[];if(!items.length){box.append(el('p','گزارش ذخیره‌شده‌ای برای این نماد موجود نیست.'));return}
    const wrap=el('div',null,'model-wrap'),table=el('table'),head=el('thead'),hr=el('tr'),body=el('tbody');
    for(const title of ['تاریخ گزارش / داده','وضعیت / تصمیم','تغییر نسبت به گزارش قبلی','گزارش'])hr.append(el('th',title));head.append(hr);
    items.forEach((item,index)=>{
        const tr=el('tr'),when=el('td',dateFmt((item.created_at||'').split('T')[0])),state=el('td',label(item.status)),change=el('td'),action=el('td');
        when.append(el('p','داده: '+dateFmt(item.as_of),'muted'));state.append(el('p',label(item.decision)),el('small',item.engine_version||'—'));
        const previous=items.slice(index+1).find(x=>x.decision);
        if(item.decision&&previous){const before=new Set(previous.failed_gates||[]),now=new Set(item.failed_gates||[]);change.textContent=(item.decision===previous.decision?'تصمیم یکسان':'تصمیم قبلی: '+label(previous.decision))+' · شروط رفع‌شده: '+fmt([...before].filter(x=>!now.has(x)).length)+' · شروط جدید: '+fmt([...now].filter(x=>!before.has(x)).length)}
        else change.textContent='مقایسه در دسترس نیست.';
        if(item.decision||['QUEUED','RUNNING'].includes(item.status)){const link=el('a',item.decision?'مشاهده':'پیگیری'),params=new URLSearchParams({symbol:item.symbol});params.set(item.decision?'analysis_id':'job_id',item.analysis_id);link.href='/?'+params.toString();action.append(link)}
        tr.append(when,state,change,action);body.append(tr);
    });table.append(head,body);wrap.append(table);box.append(wrap);
}
async function getJSON(url,options={}) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
    try {
        const r=await fetch(url,{...options,signal:controller.signal}),data=await r.json();
        if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));
        return data;
    } catch(e) {
        if(e.name==='AbortError')throw Error('زمان انتظار اتصال پایان یافت؛ می‌توانید پیگیری را ادامه دهید.');
        throw e;
    } finally {clearTimeout(timer)}
}
function rememberJob(symbol,id) {
    const url=new URL(location.href);
    url.searchParams.set('symbol',symbol);url.searchParams.set('job_id',id);url.searchParams.delete('analysis_id');
    history.replaceState(null,'',url);
    $('resume-job').dataset.jobId=id;$('resume-job').dataset.symbol=symbol;$('resume-job').hidden=false;
}
async function loadReport(symbol,id) {
    let base='/api/analysis/'+encodeURIComponent(symbol);
    const data=await getJSON(id?base+'/'+encodeURIComponent(id):base+'/latest');
    id=data.analysis_id||id;if(!id)throw Error('شناسه گزارش موجود نیست.');
    symbol=data.requested_symbol||symbol;base='/api/analysis/'+encodeURIComponent(symbol);
    renderReport(data,symbol,id);chart.setScenario(data);
    const resources=await Promise.allSettled([
        getJSON(base+'/'+encodeURIComponent(id)+'/chart'),
        getJSON(base+'/'+encodeURIComponent(id)+'/insights'),getJSON(base+'/history')]);
    if(resources[0].status==='fulfilled')chart.load(resources[0].value);
    else chart.clear('نمودار در دسترس نیست: '+resources[0].reason.message);
    if(resources[1].status==='fulfilled')renderInsights(resources[1].value);
    else $('source-health').textContent='جزئیات منابع بارگذاری نشد: '+resources[1].reason.message;
    if(resources[2].status==='fulfilled')renderHistory(resources[2].value);
    else $('analysis-history').textContent='تاریخچه بارگذاری نشد: '+resources[2].reason.message;
    const url=new URL(location.href);url.searchParams.set('symbol',symbol);url.searchParams.set('analysis_id',id);url.searchParams.delete('job_id');
    history.replaceState(null,'',url);$('resume-job').hidden=true;
}
Object.assign(names,{INTERRUPTED:'پردازش قطع شده؛ قابل اجرای مجدد',TIMED_OUT:'مهلت پردازش پایان یافته',SYMBOL_NOT_FOUND:'نماد پیدا نشد',queued:'در صف',finished:'پایان'});
function show(job) {
    $('status').textContent=label(job.status)+' · '+label(job.stage)+(job.warnings?.length?' · برخی منابع ناقص هستند':'');
    $('stages').replaceChildren(...(job.stages||[]).map(x=>el('li',label(x.name)+' · '+label(x.status)+' · '+fmt(x.seconds)+' ثانیه')));
}
async function watchJob(job) {
    const symbol=job.symbol;rememberJob(symbol,job.analysis_id);show(job);
    for(let i=0;i<300&&['QUEUED','RUNNING'].includes(job.status);i++) {
        await new Promise(resolve=>setTimeout(resolve,1000));
        job=await getJSON('/api/analyze/'+encodeURIComponent(job.analysis_id));show(job);
    }
    if(['COMPLETED','PARTIAL'].includes(job.status))await loadReport(symbol,job.analysis_id);
    else if(['QUEUED','RUNNING'].includes(job.status)) {
        $('result').textContent='پردازش ادامه دارد. دکمه ادامه پیگیری را بزنید؛ بارگذاری مجدد صفحه هم به همین تحلیل وصل می‌شود.';
        chart.clear('پردازش هنوز کامل نشده است.');
    } else {
        $('resume-job').hidden=true;
        throw Error(label(job.status)+'؛ برای تلاش مجدد دکمه تحلیل سهم را بزنید.');
    }
}
let busy=false;
async function run(latest=false,resumeId=null,reportId=null) {
    const symbol=$('symbol').value.trim();
    if(!symbol){$('status').textContent='ابتدا نماد را وارد کنید.';$('symbol').focus();return}
    if(busy)return;busy=true;
    for(const id of ['analyze','load-latest','resume-job'])$(id).disabled=true;
    $('result').replaceChildren(el('p','در حال بارگذاری…'));
    $('analysis-layers').replaceChildren();$('market-models').replaceChildren();$('source-health').replaceChildren();$('analysis-history').replaceChildren();chart.clear();
    try {
        if(latest) {
            $('status').textContent='در حال خواندن گزارش ذخیره‌شده…';
            await loadReport(symbol,reportId);$('status').textContent='گزارش ذخیره‌شده نمایش داده شد.';$('stages').replaceChildren();
        } else {
            const job=resumeId?await getJSON('/api/analyze/'+encodeURIComponent(resumeId)):
                await getJSON('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})});
            await watchJob(job);
        }
    } catch(e) {
        $('status').textContent='خطا: '+e.message;
        $('result').textContent='گزارش بارگذاری نشد. اگر تحلیل فعال است، ادامه پیگیری را بزنید.';
        chart.clear('گزارشی برای نمایش نمودار بارگذاری نشده است.');
    } finally {
        busy=false;for(const id of ['analyze','load-latest','resume-job'])$(id).disabled=false;
    }
}
$('analyze').onclick=()=>run(false);$('load-latest').onclick=()=>run(true);
$('resume-job').onclick=()=>{$('symbol').value=$('resume-job').dataset.symbol;run(false,$('resume-job').dataset.jobId)};
$('symbol').addEventListener('keydown',e=>{if(e.key==='Enter')run(false)});
const params=new URLSearchParams(location.search);
if(params.get('symbol')) {
    $('symbol').value=params.get('symbol');
    if(params.get('job_id'))run(false,params.get('job_id'));
    else run(true,null,params.get('analysis_id'));
}
