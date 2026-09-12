const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const nodes=new Map(),requests=[];let valid=true;
function node(id){if(!nodes.has(id))nodes.set(id,{handlers:{},children:[],checked:false,disabled:false,value:'1',open:false,
 addEventListener(k,fn){this.handlers[k]=fn;},replaceChildren(){this.children=[];},append(child){this.children.push(child);},
 showModal(){this.open=true;},close(){this.open=false;this.handlers.close?.();},focus(){}});return nodes.get(id);}
let stage='ready';const data=()=>({ticket:'c'.repeat(32),stage,message:stage,printer:'A1 mini',filament:'PLA',plates:[{plate:1,seconds:120,grams:2}]});
const context=vm.createContext({console,Map,Math,Number,Promise,document:{getElementById:node,createElement:()=>({})},window:{},setTimeout,
 fetch:async(url,options={})=>{requests.push({url,...options});return {ok:true,json:async()=>url.endsWith('session')?{token:'token'}:data()};}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../remote-print-ui.js'),'utf8'),context);
const job={id:'a'.repeat(32),name:'model',manifest_sha256:'current'},dialog=node('remotePrintConfirm');
(async()=>{
 await context.window.SkeleRemotePrint.open(job,{ready:true},()=>valid);
 assert.equal(dialog.open,true);assert.equal(node('remotePrintStart').disabled,true);
 await node('remotePrintCancel').handlers.click();assert.equal(dialog.open,false);
 assert.equal(requests.filter(r=>r.url.endsWith('/start')).length,0,'cancel never sends a start');
 await context.window.SkeleRemotePrint.open(job,{ready:true},()=>valid);
 node('remotePrintBedClear').checked=true;node('remotePrintBedClear').handlers.change();
 valid=false;await node('remotePrintStart').handlers.click();
 assert.equal(requests.filter(r=>r.url.endsWith('/start')).length,0,'changed model cannot start');
 valid=true;stage='started';await node('remotePrintStart').handlers.click();
 await node('remotePrintStart').handlers.click();
 const sent=requests.filter(r=>r.url.endsWith('/start'));assert.equal(sent.length,1);
 assert.deepEqual(JSON.parse(sent[0].body),{ticket:'c'.repeat(32),plate:1,accepted:true,bed_clear:true});
 assert.equal(node('remotePrintStart').disabled,true);
 assert.ok(!requests.some(r=>r.url.endsWith('/open-print')));
 console.log('PASS: explicit bed confirmation, cancel, stale selection, one start only and no Bambu GUI fallback');
})().catch(error=>{console.error(error);process.exitCode=1;});
