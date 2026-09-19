const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
  constructor(){this.hidden=false;this.disabled=false;this.textContent='';this.innerHTML='';this.className='';this.handlers={};this.dataset={};this.style={};this.classes=new Set();this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c)};}
  setAttribute(k,v){this[k]=v;}
  cloneNode(){return new Element();}
  remove(){this.removed=true;}
  setPointerCapture(){}
  showModal(){this.open=true;} close(){this.open=false;} focus(){} append(...nodes){appended.push(...nodes);}
  addEventListener(type,fn){this.handlers[type]=fn;}
}
const elements=new Map(['poseSnapshots','snapshotList','snapshotFlash','resetView','snapshotEditor','snapshotEditorGrid','snapshotEditorScroll','snapshotEditorStatus','snapshotEditorCancel','snapshotEditorDone'].map(id=>[id,new Element()]));
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
const context=vm.createContext({document,localStorage,requestAnimationFrame:fn=>setTimeout(fn,16),cancelAnimationFrame:clearTimeout,setTimeout,clearTimeout,Date:TestDate,window:{innerWidth:375,addEventListener:(type,fn)=>windowHandlers[type]=fn},Math,module:{exports:{}},console});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../pose-snapshots.js'),'utf8'),context);
const api={motion:()=>motion,model:()=>currentModel,camera:()=>({yaw:1,pitch:2,roll:3,distanceRatio:1.5,centerOffset:[0,0,0]}),setCamera:value=>cameraSet=value,
  resetView:()=>resetCount++,capture:()=> 'data:image/jpeg;base64,preview',requestRender(){}};
const snapshots=context.module.exports.createMobilePoseSnapshots(api);snapshots.sync();
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

const list=elements.get('snapshotList'),grid=elements.get('snapshotEditorGrid'),editor=elements.get('snapshotEditor'),scroll=elements.get('snapshotEditorScroll');
scroll.scrollTop=0;scroll.getBoundingClientRect=()=>({left:0,right:375,top:100,bottom:600,width:375,height:500});
const cards=new Map();
function card(id,index=0){if(!cards.has(id)){const c=new Element();c.dataset.id=id;c.closest=s=>['.snapshotCard','.snapshotEditCard'].includes(s)?c:null;cards.set(id,c);}const c=cards.get(id);c.getBoundingClientRect=()=>({left:index*160,top:110,right:index*160+150,bottom:260,width:150,height:150});return c;}
grid.querySelectorAll=s=>s==='.dragTarget'?[]:snapshots.items().map((item,i)=>card(item.id,i));
function down(edit=false){advance(600);const e={target:card(snapshots.items()[0].id),pointerId:1,pointerType:'touch',button:0,clientX:50,clientY:150,preventDefault(){}};documentHandlers.pointerdown(e);(edit?grid:list).handlers.pointerdown(e);return e;}
function open(){const e=down();advance(451);documentHandlers.pointerup(e);assert.equal(editor.open,true);advance(600);}
function remove(){grid.handlers.click({target:{closest:s=>s==='.snapshotEditCard'?card(snapshots.items()[0].id):s==='.snapshotEditDelete'?{}:null}});}
const initial=stored.get('skelecad.poseSnapshots.v1');
let e=down();documentHandlers.pointermove({...e,clientX:90});advance(500);documentHandlers.pointerup(e);assert.ok(!editor.open);
open();remove();assert.ok(grid.innerHTML.includes(' pendingDelete'));assert.equal((grid.innerHTML.match(/<article/g)||[]).length,2);remove();assert.ok(!grid.innerHTML.includes(' pendingDelete'));remove();assert.equal(stored.get('skelecad.poseSnapshots.v1'),initial);elements.get('snapshotEditorCancel').handlers.click();assert.equal(snapshots.items().length,2);assert.equal(stored.get('skelecad.poseSnapshots.v1'),initial);
open();remove();elements.get('snapshotEditorDone').handlers.click();assert.equal(snapshots.items().length,1);
advance(600);list.handlers.click({target:addTarget});const first=snapshots.items()[0].id;
open();e=down(true);documentHandlers.pointermove({...e,clientY:110});assert.equal(scroll.scrollTop,40);advance(500);documentHandlers.pointerup(e);assert.equal(appended.length,0);
e=down(true);advance(451);assert.ok(appended.length>0);documentHandlers.lostpointercapture({...e,target:e.target});assert.ok(!appended.at(-1).removed);
documentHandlers.pointermove({...e,clientX:310,clientY:150});documentHandlers.pointerup({...e,clientX:310,clientY:150});assert.equal(snapshots.items()[0].id,first);elements.get('snapshotEditorDone').handlers.click();assert.equal(snapshots.items()[1].id,first);
open();const oldWrite=localStorage.setItem;localStorage.setItem=()=>{throw Error('quota');};remove();elements.get('snapshotEditorDone').handlers.click();assert.equal(editor.open,true);assert.equal(snapshots.items().length,2);localStorage.setItem=oldWrite;editor.handlers.cancel({preventDefault(){}});assert.equal(editor.open,false);
open();currentModel='changed';snapshots.sync();assert.equal(editor.open,false);
console.log('PASS: mobile hold/swipe, draft reorder/delete, commit/cancel, capture transfer, quota rollback and model isolation');
