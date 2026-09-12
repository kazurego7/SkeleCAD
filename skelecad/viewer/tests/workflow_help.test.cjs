const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
let step='0',phone=true;const observers=[],events={};
function node(){return {dataset:{},handlers:{},children:[],open:false,addEventListener(k,fn){this.handlers[k]=fn;},replaceChildren(){this.children=[];},append(...items){this.children.push(...items);},showModal(){this.open=true;},close(){this.open=false;this.handlers.close?.();},focus(){this.focused=true;},getBoundingClientRect(){return {left:10,right:300,top:10,bottom:400};}};}
const nodes=Object.fromEntries(['gl','modelSelect','workflowHelpOpen','workflowHelp','workflowHelpClose','workflowHelpTitle','workflowHelpBody'].map(id=>[id,node()]));
const context=vm.createContext({console,Map,Math,Number,Date,setTimeout,clearTimeout,MutationObserver:class{constructor(fn){observers.push(fn);}observe(){}},
 document:{documentElement:{getAttribute:()=>step},getElementById:id=>nodes[id],createElement:node,addEventListener(){}},
 window:{addEventListener(k,fn){events[k]=fn;},matchMedia:()=>({get matches(){return phone;},addEventListener(){}})}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../mobile-ui.js'),'utf8'),context);
const text=n=>[n.textContent||'',...n.children.map(text)].join(' '),dialog=nodes.workflowHelp;
for(const [i,title] of ['画像','モデル','パーツ分割','可動域','プリント準備'].entries()){
 step=String(i);nodes.workflowHelpOpen.handlers.click();assert.equal(dialog.open,true);assert.equal(nodes.workflowHelpTitle.textContent,title+'の操作');assert.ok(text(nodes.workflowHelpBody).length>60);nodes.workflowHelpClose.handlers.click();assert.equal(dialog.open,false);assert.equal(nodes.workflowHelpOpen.focused,true);
}
step='2';nodes.workflowHelpOpen.handlers.click();assert.match(text(nodes.workflowHelpBody),/長押し/);assert.match(text(nodes.workflowHelpBody),/ダブルタップ/);
phone=false;events.resize();assert.match(text(nodes.workflowHelpBody),/右クリック/);assert.doesNotMatch(text(nodes.workflowHelpBody),/長押し/);
step='3';observers.forEach(fn=>fn());assert.equal(nodes.workflowHelpTitle.textContent,'可動域の操作');assert.match(text(nodes.workflowHelpBody),/プリント準備について/);assert.match(text(nodes.workflowHelpBody),/Bambu Studio/);
dialog.handlers.click({target:dialog,clientX:20,clientY:20});assert.equal(dialog.open,true,'clicks within the dialog do not dismiss');dialog.handlers.click({target:dialog,clientX:0,clientY:0});assert.equal(dialog.open,false);
console.log('PASS: five contextual help topics, phone/mouse instructions, live step changes, print help, backdrop dismissal and focus restoration');
