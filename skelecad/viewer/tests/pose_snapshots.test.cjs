const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
  constructor(){this.hidden=false;this.disabled=false;this.textContent='';this.innerHTML='';this.className='';this.handlers={};this.dataset={};this.style={};this.classes=new Set();this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c)};}
  setAttribute(k,v){this[k]=v;}
  cloneNode(){return new Element();}
  remove(){this.removed=true;}
  setPointerCapture(){}
  addEventListener(type,fn){this.handlers[type]=fn;}
}
const elements=new Map(['poseSnapshots','snapshotList','snapshotFlash','resetView'].map(id=>[id,new Element()]));
const stored=new Map(),localStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)};
const timers=new Map(),deadlines=new Map(),documentHandlers={},windowHandlers={};let nextTimer=1,clock=Date.now();
class TestDate extends Date{static now(){return clock;}}
function advance(ms){clock+=ms;for(const [id,at] of [...deadlines])if(at<=clock){const fn=timers.get(id);timers.delete(id);deadlines.delete(id);fn?.();}}
const setTimeout=(fn,delay)=>{const id=nextTimer++;timers.set(id,fn);deadlines.set(id,clock+delay);return id;},clearTimeout=id=>{timers.delete(id);deadlines.delete(id);};
let pose={hip:[12,0,0],ankle:[0,0,0]},restored=null,cameraSet=null,resetCount=0,active=true,currentModel='model-a';
const joints=[{name:'hip',part:'leg',parent:'torso',center:[0,0,0],direction:[0,1,0]},{name:'ankle',part:'foot',parent:'leg',center:[0,0,-10],direction:[0,0,-1]}];
const motion={isActive:()=>active,joints:()=>joints,reviewState:()=>({pose}),restore:value=>{restored=value;return {restored:value.joints.length,total:2};}};
const appended=[];
const document={body:{append:(...nodes)=>appended.push(...nodes)},addEventListener:(type,fn)=>documentHandlers[type]=fn,getElementById:id=>elements.get(id),createElement:()=>new Element()};
const context=vm.createContext({document,localStorage,requestAnimationFrame:fn=>fn(),setTimeout,clearTimeout,Date:TestDate,window:{innerWidth:375,addEventListener:(type,fn)=>windowHandlers[type]=fn},Math,module:{exports:{}},console});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../pose-snapshots.js'),'utf8'),context);
const api={motion:()=>motion,model:()=>currentModel,camera:()=>({yaw:1,pitch:2,roll:3,distanceRatio:1.5,centerOffset:[0,0,0]}),setCamera:value=>cameraSet=value,
  resetView:()=>resetCount++,capture:()=> 'data:image/jpeg;base64,preview',requestRender(){}};
const snapshots=context.module.exports.createPoseSnapshots(api);snapshots.sync();
assert.equal(elements.get('poseSnapshots').hidden,false);assert.equal(elements.get('resetView').hidden,false);assert.doesNotMatch(elements.get('snapshotList').innerHTML,/正面/);
assert.match(elements.get('snapshotList').innerHTML,/snapshotAddCard/);assert.match(elements.get('snapshotList').innerHTML,/snapshotCameraIcon/);
assert.doesNotMatch(elements.get('snapshotList').innerHTML,/新規追加/);assert.doesNotMatch(elements.get('snapshotList').innerHTML,/data-default/);
assert.doesNotMatch(elements.get('snapshotList').innerHTML,/<small>|基準の姿勢|関節を変更/);
assert.doesNotMatch(elements.get('snapshotList').innerHTML,/<img/);
let dragPrevented=false;const defaultDragTarget={closest:selector=>selector==='.snapshotCard'?{dataset:{id:'add'}}:null};
elements.get('poseSnapshots').handlers.dragstart({target:defaultDragTarget,preventDefault:()=>dragPrevented=true});assert.equal(dragPrevented,true,'default thumbnail cannot begin a native file drag');
const addArticle={dataset:{id:'add'}},addTarget={closest:selector=>selector==='.snapshotCard'?addArticle:null};
elements.get('snapshotList').handlers.click({target:addTarget});
assert.equal(snapshots.items().length,1);assert.equal(snapshots.items()[0].joints[0].angles[0],12);assert.match(elements.get('snapshotList').innerHTML,/data:image\/jpeg/);
assert.equal(elements.get('snapshotFlash').hidden,false);assert.equal(elements.get('snapshotFlash').className,'active');
timers.get(Math.max(...timers.keys()))();assert.equal(elements.get('snapshotFlash').hidden,true);assert.equal(elements.get('snapshotFlash').className,'');
pose={hip:[24,0,0],ankle:[0,0,0]};elements.get('snapshotList').handlers.click({target:addTarget});
assert.deepEqual(JSON.parse(JSON.stringify(snapshots.items().map(item=>item.name))),['スナップショット 2','スナップショット 1']);
const rendered=elements.get('snapshotList').innerHTML;
assert.ok(!rendered.includes('data-id="front"'));
assert.ok(rendered.indexOf('snapshotAddCard')<rendered.indexOf(`data-id="${snapshots.items()[0].id}"`));
assert.ok(rendered.indexOf(`data-id="${snapshots.items()[0].id}"`)<rendered.indexOf(`data-id="${snapshots.items()[1].id}"`));
assert.doesNotMatch(rendered,/<strong>|<small>|>姿勢|>正面|>1<|>2</);
const list=elements.get('snapshotList'),panel=elements.get('poseSnapshots');
let panelBounds={left:0,top:500,right:375,bottom:590,width:375,height:90};
panel.getBoundingClientRect=()=>panelBounds;panel.scrollLeft=0;panel.scrollTop=0;
const cards=new Map();
list.querySelectorAll=selector=>{
 const result=['add',...snapshots.items().map(item=>item.id)].map((id,index)=>{
  if(!cards.has(id)){const card=new Element();card.dataset.id=id;card.closest=s=>s==='.snapshotCard'?card:null;cards.set(id,card);}
  const card=cards.get(id),horizontal=panelBounds.width>panelBounds.height;
  card.getBoundingClientRect=()=>horizontal?{left:10+index*108,top:506,width:100,height:76}:{left:panelBounds.left+6,top:10+index*108,width:100,height:76};return card;
 });return selector==='.dragTarget'?result.filter(c=>c.classes.has('dragTarget')):result;
};
function press(id=snapshots.items()[0].id,extra={}){
 advance(600);const target=list.querySelectorAll('.snapshotCard').find(c=>c.dataset.id===id),r=target.getBoundingClientRect();
 const e={target,button:0,pointerId:1,pointerType:'touch',clientX:r.left+r.width/2,clientY:r.top+r.height/2,preventDefault(){},...extra};
 documentHandlers.pointerdown(e);list.handlers.pointerdown(e);return e;
}
function move(e,x,y){const next={...e,clientX:x,clientY:y};documentHandlers.pointermove(next);return next;}
function release(e){documentHandlers.pointerup(e);}
const ids=()=>JSON.stringify(snapshots.items().map(item=>item.id));
assert.doesNotMatch(rendered,/snapshotDelete/);
let e=press();advance(1500);release(e);list.handlers.click({target:e.target});
assert.equal(restored.id,snapshots.items()[0].id,'stationary press restores without deletion');assert.equal(snapshots.items().length,2);
const firstBeforeMove=snapshots.items()[0];
e=press(firstBeforeMove.id);e=move(e,340,544);assert.equal(appended.at(-1).textContent,'並べ替え');release(e);
assert.equal(snapshots.items()[1].id,firstBeforeMove.id,'inside drag reorders');
assert.deepEqual(JSON.parse(stored.get('skelecad.poseSnapshots.v1')).map(item=>item.order),[0,1]);
e=press(firstBeforeMove.id,{pointerType:'mouse'});release(move(e,40,544));assert.equal(snapshots.items()[0].id,firstBeforeMove.id,'mouse reordering');
for(const distance of [20,79]){const before=ids();e=press();e=move(e,170,500-distance);assert.equal(appended.at(-1).textContent,'離すと元に戻ります');release(e);assert.equal(ids(),before,'near outside cancels');}
e=press();e=move(e,170,400);assert.equal(appended.at(-1).textContent,'離すと削除');assert.equal(appended.at(-2).dataset.delete,'true');release(move(e,40,544));assert.equal(snapshots.items().length,2,'returning inside disarms deletion');
e=press();e=move(e,170,400);release({...e,clientY:490});assert.equal(snapshots.items().length,2,'release position is authoritative');
for(const cancel of [e=>documentHandlers.pointercancel(e),e=>documentHandlers.lostpointercapture(e),()=>windowHandlers.blur(),()=>documentHandlers.visibilitychange(),()=>snapshots.render(),e=>documentHandlers.pointerdown({...e,pointerId:2})]){
 const before=ids();e=press();e=move(e,170,400);cancel(e);release(e);documentHandlers.pointerup({pointerId:2});assert.equal(ids(),before,'interruptions cancel deletion');assert.ok(appended.at(-1).removed&&appended.at(-2).removed);
}
e=press();e=move(e,170,400);currentModel='other-model';release(e);currentModel='model-a';assert.equal(snapshots.items().length,2,'model change cancels');
panelBounds={left:1100,top:0,right:1230,bottom:800,width:130,height:800};e=press();release(move(e,1160,700));assert.equal(snapshots.items().length,2,'long desktop drag inside never deletes');
panelBounds={left:0,top:500,right:375,bottom:590,width:375,height:90};
e=press();e=move(e,170,420);assert.equal(snapshots.items().length,2,'crossing threshold alone never deletes');release(e);assert.equal(snapshots.items().length,1,'release 80px outside deletes exactly one');assert.equal(JSON.parse(stored.get('skelecad.poseSnapshots.v1')).length,1);
const beforeGhost=restored;list.handlers.click({target:e.target});assert.equal(restored,beforeGhost,'post-drag click suppressed');
e=press();release(move(e,170,400));assert.equal(snapshots.items().length,0);advance(600);
snapshots.clearSelection();assert.doesNotMatch(elements.get('snapshotList').innerHTML,/aria-current="true"/);
currentModel='model-b';snapshots.sync();assert.equal(snapshots.items().length,0,'another model starts with its own empty snapshot list');
elements.get('snapshotList').handlers.click({target:addTarget});assert.equal(snapshots.items().length,1);assert.equal(snapshots.items()[0].model,'model-b');
currentModel='model-a';snapshots.sync();assert.equal(snapshots.items().length,0,'switching back does not show snapshots saved for another model');
for(const side of ['original','negative_x','positive_x']){
  currentModel='job:same:'+side;snapshots.sync();assert.equal(snapshots.items().length,0);
  elements.get('snapshotList').handlers.click({target:addTarget});
}
for(const side of ['original','negative_x','positive_x']){
  currentModel='job:same:'+side;snapshots.sync();assert.equal(snapshots.items().length,1);
  assert.equal(snapshots.items()[0].model,currentModel);
}
active=false;snapshots.sync();assert.equal(elements.get('poseSnapshots').hidden,true);assert.equal(elements.get('resetView').hidden,false);
console.log('PASS: image snapshots persist per model with pose/camera, pointer reordering, restore, drag-away deletion with cancellation and selection reset without a default card');
