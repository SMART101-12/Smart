const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.textContent = ''; this.value = 'TEST'; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
}
module.exports = (async () => {
    const nodes = Object.fromEntries(['codal-symbol','codal-local','codal-sync','codal-status','codal-results','codal-help'].map(id => [id,new Element('div')]));
    const calls = [];
    const replies = [];
    const context = vm.createContext({URL, URLSearchParams, location: {search:''},
        document:{createElement:tag => new Element(tag), getElementById:id => nodes[id]},
        fetch:async url => { calls.push(url); const reply = replies.shift(); return {ok:true,json:async () => reply || ({monthly_sales:[],financial_data:[],sync:{status:'PARTIAL'}})}; }});
    vm.runInContext(fs.readFileSync('src/smart/codal-reports.js','utf8'),context);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls.length,1);
    assert.ok(calls[0].endsWith('sync=false'));
    assert.equal(nodes['codal-local'].disabled,false);
    vm.runInContext(`renderCodal({monthly_sales:[{period:'1404/01/31',publish_date:'1404/02/05',products:[],sales_value:{value:100,unit:'IRR',source_records:[{source_url:'javascript:alert(1)',report_id:'bad'},{source_url:'https://www.codal.ir/Reports/a',report_id:'good'}]}}],financial_data:[],product_sales:[],quarterly_financials:[]})`,context);
    const flatten = node => [node,...node.children.flatMap(flatten)];
    const all = flatten(nodes['codal-results']);
    assert.equal(all.filter(n => n.tag === 'table').length,1);
    const links = all.filter(n => n.tag === 'a');
    assert.equal(links.length,1); assert.equal(links[0].href,'https://www.codal.ir/Reports/a');
    assert.ok(all.some(n => n.textContent.includes('100 IRR') || n.textContent.includes('۱۰۰ IRR')));
    vm.runInContext(`renderCodal({symbol:'TEST',assistance:{status:'WAITING_FOR_USER',session_id:'session-token'},sync:{status:'PARTIAL'}})`,context);
    const help = flatten(nodes['codal-help']);
    const refresh = help.find(n => n.tag === 'button' && n.type === 'button');
    const form = help.find(n => n.tag === 'form');
    const input = help.find(n => n.tag === 'input');
    const submit = help.find(n => n.tag === 'button' && n.type === 'submit');
    replies.push({image:'data:image/png;base64,aW1hZ2U='});
    await refresh.onclick();
    assert.equal(help.find(n => n.tag === 'img').hidden,false);
    assert.ok(calls.at(-1).endsWith('/image'));
    replies.push({verified:false}); input.value = 'wrong';
    await form.onsubmit({preventDefault(){}});
    assert.equal(submit.disabled,false);
    assert.ok(help.some(n => n.textContent.includes('پذیرفته نشد')));
    replies.push({verified:true,reports:{symbol:'TEST',sync:{status:'SUCCESS'},assistance:{status:'NOT_REQUIRED'}}}); input.value='1234';
    await form.onsubmit({preventDefault(){}});
    assert.equal(nodes['codal-help'].children.length,0);
    assert.equal(nodes['codal-sync'].disabled,false);
    assert.ok(nodes['codal-status'].textContent.includes('ذخیره'));
    return 'Codal UI: local cache, safe tables, captcha image, wrong-code feedback and verified resume passed';
})();
