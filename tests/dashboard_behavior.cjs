// Exercise the actual dashboard script without requiring a browser installation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();
const ctx=new Proxy({}, {get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
function node(){return {childNodes:[],dataset:{},classList:{remove(){},toggle(){}},events:{},append(...v){this.childNodes.push(...v)},replaceChildren(...v){this.childNodes=v},addEventListener(k,v){this.events[k]=v},setAttribute(k,v){this[k]=v},getContext(){return ctx},getBoundingClientRect(){return {left:0,width:900,height:400}},setPointerCapture(){},parentElement:{},textContent:''}}
const ranges=['30','90','250','all'].map(range=>Object.assign(node(),{dataset:{range}}));
const sandbox={Intl,URL,URLSearchParams,console,setTimeout,clearTimeout,AbortController,document:{getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)},createElement:node,querySelectorAll(){return ranges}},ResizeObserver:class{observe(){}},window:{devicePixelRatio:1},location:{search:'',href:'http://localhost/'},history:{replaceState(){}},fetch(){throw Error('Unexpected network request')}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('src/smart/dashboard.js','utf8'),sandbox);
vm.runInContext(`
chart.load({source:'fixture',as_of:'2026-09-27',bars:Array.from({length:250},(_,i)=>({source_date:'2026-09-27',open:100+i,close:100.75+i,high:102+i,low:99+i,volume:1000+i}))});
if(chart.size!==90||chart.start!==160)throw Error('Initial range incorrect');
document.getElementById('zoom-in').onclick();
if(chart.size!==72)throw Error('Zoom button did not change visible range');
chart.canvas.events.wheel({deltaY:-1,clientX:400,preventDefault(){}});
if(chart.size>=72)throw Error('Mouse wheel did not zoom');
chart.canvas.events.pointerdown({pointerType:'mouse',clientX:400,pointerId:1});
chart.canvas.events.pointermove({clientX:650});
if(chart.start>=160)throw Error('Dragging did not pan');
chart.canvas.events.pointerup();
chart.canvas.events.keydown({key:'Home',preventDefault(){}});
if(chart.size!==90||chart.start!==160)throw Error('Keyboard reset incorrect');
chart.range('all');chart.zoom(10);if(chart.size!==250||chart.start!==0)throw Error('Range overflow');
chart.range(30);chart.zoom(.001);if(chart.size!==5)throw Error('Minimum zoom incorrect');
if(fmt(3421.057143).includes('٫')||fmt(null)!=='—')throw Error('Numeric formatting incorrect');
if(!displayText('ratio 1.2').includes('≈')||displayText('SMART-ANALYSIS-2.1')!=='SMART-ANALYSIS-2.1')throw Error('Text formatting incorrect');
chart.setScenario({entry_exit:{conditional:{entry_zone_if_confirmed:[120,121.5],stop_if_entered:110,target_1_if_entered:135}}});
if(chart.levels.length!==3||chart.levels[0][1]!==121.5)throw Error('Conditional level precision lost');
document.getElementById('chart-levels').onclick();document.getElementById('chart-mode').onclick();
if(!chart.showLevels||chart.mode!=='candle')throw Error('Chart mode controls failed');
`,sandbox);
assert.equal(nodes.get('chart-empty').textContent,'');
console.log('Dashboard behavior passed: zoom, wheel, pan, keyboard, limits, formatting.');
const calls=[];
sandbox.fetch=async(url,options)=>{calls.push({url,method:options.method||'GET'});return {ok:true,json:async()=>url.endsWith('/chart')?{bars:[]}:{analysis_id:'fixture',requested_symbol:'TEST',status:'PARTIAL',as_of:'2026-09-27'}}};
vm.runInContext("watchJob({analysis_id:'fixture',symbol:'TEST',status:'PARTIAL'})",sandbox).then(()=>{
    assert.equal(calls.length,4);
    assert.ok(calls.every(call=>call.method==='GET'));
    assert.equal(nodes.get('resume-job').hidden,true);
    console.log('Saved job resume passed without starting another analysis.');
}).catch(error=>{console.error(error);process.exitCode=1});
