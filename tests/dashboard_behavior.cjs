// Exercise the actual dashboard script without requiring a browser installation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map();
const ctx=new Proxy({}, {get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
function node(){return {childNodes:[],dataset:{},classList:{remove(){},toggle(){}},events:{},append(...v){this.childNodes.push(...v)},replaceChildren(...v){this.childNodes=v},addEventListener(k,v){this.events[k]=v},getContext(){return ctx},getBoundingClientRect(){return {left:0,width:900,height:400}},setPointerCapture(){},parentElement:{},textContent:''}}
const ranges=['30','90','250','all'].map(range=>Object.assign(node(),{dataset:{range}}));
const sandbox={Intl,URL,URLSearchParams,console,setTimeout,document:{getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)},createElement:node,querySelectorAll(){return ranges}},ResizeObserver:class{observe(){}},window:{devicePixelRatio:1},location:{search:'',href:'http://localhost/'},history:{replaceState(){}},fetch(){throw Error('Unexpected network request')}};
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
`,sandbox);
assert.equal(nodes.get('chart-empty').textContent,'');
console.log('Dashboard behavior passed: zoom, wheel, pan, keyboard, limits, formatting.');
