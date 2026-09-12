const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
let now=0,step='2',active=true,observer;const timers=new Map(),handlers={},actions=[];
function target(name){return {dataset:name?{markerName:name}:{},closest(s){return s==='.partitionMarker'&&name?this:null;},setPointerCapture(){},addEventListener(){}};}
const canvas=target(),marker=target('left'),other=target('right'),input={closest:s=>s.startsWith('input')?input:null};
let timerId=0;
const context=vm.createContext({console,Map,Math,Date:{now:()=>now},setTimeout(fn,ms){const id=++timerId;timers.set(id,{fn,at:now+ms});return id;},clearTimeout:id=>timers.delete(id),
  MutationObserver:class{constructor(fn){observer=fn;}observe(){}},
  document:{documentElement:{getAttribute:()=>step},getElementById:id=>id==='gl'?canvas:id==='modelSelect'?target():null,addEventListener(type,fn){(handlers[type]??=[]).push(fn);}},
  window:{addEventListener(){},matchMedia:()=>({matches:true,addEventListener(){}}),SkelePartition:{isActive:()=>active,addAt:(x,y)=>actions.push(['add',x,y]),removeNamed:name=>actions.push(['delete',name]),toggleNamed:name=>actions.push(['pair',name])}}
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../mobile-ui.js'),'utf8'),context);
function emit(type,target=canvas,extra={}){const e={target,pointerType:'touch',pointerId:1,clientX:100,clientY:100,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...extra};for(const fn of handlers[type]||[])fn(e);return e;}
function advance(ms){now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}}
function clear(){emit('pointercancel');emit('pointercancel',canvas,{pointerId:2});actions.length=0;advance(1100);}
function tap(t){emit('pointerdown',t);advance(40);emit('pointerup',t);}
emit('pointerdown');advance(599);assert.equal(actions.length,0);advance(1);assert.deepEqual(actions,[['add',100,100]]);advance(1000);emit('pointerup');assert.equal(actions.length,1,'holding only adds once');clear();
emit('pointerdown',marker);advance(600);emit('pointerup',marker);assert.deepEqual(actions,[['delete','left']]);clear();
tap(marker);advance(90);tap(marker);assert.deepEqual(actions,[['pair','left']]);assert.equal(emit('dblclick',marker).stopped,true,'native double click must not toggle twice');clear();
tap(marker);advance(90);tap(other);assert.equal(actions.length,0,'different markers are not a double tap');clear();
tap(marker);advance(350);tap(marker);assert.equal(actions.length,0,'slow taps are not a double tap');clear();
for(const cancel of [()=>emit('pointermove',canvas,{clientX:109}),()=>emit('pointerdown',canvas,{pointerId:2}),()=>emit('pointercancel'),()=>emit('lostpointercapture'),()=>{step='3';observer();}]){
  step='2';observer();emit('pointerdown');cancel();advance(700);assert.equal(actions.length,0,'moving, multitouch, capture loss and navigation cancel long press');clear();
}
step='2';observer();emit('pointerdown');advance(300);observer();advance(300);assert.equal(actions.length,1,'a status refresh on the same step does not cancel a hold');clear();
step='3';observer();emit('pointerdown',marker);advance(700);emit('pointerup',marker);assert.equal(actions.length,0,'articulation never edits markers');clear();
step='2';observer();emit('pointerdown',marker,{pointerType:'mouse'});advance(700);emit('pointerup',marker,{pointerType:'mouse'});assert.equal(actions.length,0,'mouse input retains its existing handlers');assert.equal(emit('contextmenu',marker,{pointerType:'mouse'}).prevented,undefined);clear();
emit('pointerdown',marker);assert.equal(emit('contextmenu',marker).prevented,true);assert.equal(actions.length,0,'native contextmenu cannot cause an early delete');clear();
assert.equal(emit('selectstart',marker).prevented,true);assert.equal(emit('selectstart',input).prevented,undefined,'text fields remain editable');
console.log('PASS: long press add/delete, double tap symmetry, native-event suppression, drift/multitouch/cancel/navigation and text-field exceptions');
