const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),calls=[];
function element(){return {textContent:'',dataset:{},disabled:false,hidden:false,children:[],append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items}}}
const position={id:'fixture',symbol:'TEST',mode:'PAPER',status:'OPEN',remaining_quantity:10,realized_net_pnl:0};
const sandbox={Intl,AbortController,setTimeout,clearTimeout,console,crypto:{randomUUID:()=>String(Math.random())},
    FormData:class{constructor(form){return Object.entries(form.values)}},
    document:{getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)},createElement:element},
    async fetch(url,options){calls.push({url,options});return {ok:true,json:async()=>url.endsWith('/review')?
        {action:'TP1_REVIEW',as_of:'2026-10-09'}:url==='/api/positions'&&options.method==='GET'?
        {positions:[position]}:position}}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('src/smart/positions.js','utf8'),sandbox);
module.exports=(async()=>{
    await vm.runInContext('plist()',sandbox);
    assert.equal(nodes.get('positions-list').children.length,1);
    await vm.runInContext("pselect('fixture')",sandbox);
    assert.equal(nodes.get('selected-position').hidden,false);
    await nodes.get('position-review').onclick();
    assert.ok(nodes.get('position-review-result').textContent.includes('هدف اول'));
    assert.ok(calls.some(c=>c.url.endsWith('/review')&&c.options.method==='POST'));
    const form=element(),button=element();form.values={fill_date:'2026-10-09',price:'110',quantity:'2',fee:'1',reason:'TP1'};form.querySelector=()=>button;
    sandbox.testEvent={preventDefault(){},target:form};
    await vm.runInContext("psubmit(testEvent,'exit')",sandbox);
    await vm.runInContext("psubmit(testEvent,'exit')",sandbox);
    const submissions=calls.filter(c=>c.url.endsWith('/fills')).map(c=>JSON.parse(c.options.body));
    assert.equal(submissions[0].request_id,submissions[1].request_id);
    assert.equal(submissions[0].quantity,2);
    assert.equal(button.disabled,false);
    assert.ok(nodes.get('position-status').textContent.includes('هیچ سفارشی'));
    console.log('Position UI passed: listing, selecting, review and idempotent form submission.');
})();
