const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
  constructor(){this.hidden=false;this.disabled=false;this.textContent='';this.innerHTML='';this.className='';this.handlers={};}
  addEventListener(type,fn){this.handlers[type]=fn;}
}
const elements=new Map(['poseSnapshots','snapshotList','snapshotFlash','resetView'].map(id=>[id,new Element()]));
const stored=new Map(),localStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)};
const timers=new Map();let nextTimer=1;
const setTimeout=(fn)=>{const id=nextTimer++;timers.set(id,fn);return id;},clearTimeout=id=>timers.delete(id);
let pose={hip:[12,0,0],ankle:[0,0,0]},restored=null,cameraSet=null,resetCount=0,active=true,currentModel='model-a';
const joints=[{name:'hip',part:'leg',parent:'torso',center:[0,0,0],direction:[0,1,0]},{name:'ankle',part:'foot',parent:'leg',center:[0,0,-10],direction:[0,0,-1]}];
const motion={isActive:()=>active,joints:()=>joints,reviewState:()=>({pose}),restore:value=>{restored=value;return {restored:value.joints.length,total:2};}};
const document={getElementById:id=>elements.get(id),createElement:()=>({width:0,height:0,getContext:()=>({fillRect(){},drawImage(){}}),toDataURL:()=> 'data:image/jpeg;base64,preview'})};
const context=vm.createContext({document,localStorage,requestAnimationFrame:fn=>fn(),setTimeout,clearTimeout,Date,Math,module:{exports:{}},console});
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
const firstBeforeMove=snapshots.items()[0],secondBeforeMove=snapshots.items()[1],classes=new Set();
const firstArticle={dataset:{id:firstBeforeMove.id},classList:{add:value=>classes.add(value)}};
const firstDragTarget={closest:selector=>selector==='.snapshotCard'?firstArticle:null},transfer={effectAllowed:'',dropEffect:'',values:{},setData(type,value){this.values[type]=value;}};
let savedDragPrevented=false;elements.get('snapshotList').handlers.dragstart({target:firstDragTarget,dataTransfer:transfer,preventDefault:()=>savedDragPrevented=true});
assert.equal(savedDragPrevented,false);assert.equal(transfer.values['application/x-skelecad-snapshot'],firstBeforeMove.id);assert.equal(transfer.values['Files'],undefined);assert.ok(classes.has('dragging'));
const secondArticle={dataset:{id:secondBeforeMove.id},getBoundingClientRect:()=>({top:0,height:100})},secondDragTarget={closest:selector=>selector==='.snapshotCard'?secondArticle:null};
elements.get('snapshotList').handlers.drop({target:secondDragTarget,dataTransfer:transfer,clientY:90,preventDefault(){}});
assert.equal(snapshots.items()[1].id,firstBeforeMove.id);assert.deepEqual(JSON.parse(stored.get('skelecad.poseSnapshots.v1')).map(item=>item.order),[0,1]);
elements.get('snapshotList').handlers.dragstart({target:firstDragTarget,dataTransfer:transfer,preventDefault(){}});
elements.get('snapshotList').handlers.drop({target:addTarget,dataTransfer:transfer,clientY:0,preventDefault(){}});assert.equal(snapshots.items()[0].id,firstBeforeMove.id,'drop on fixed cards moves to first saved position');
elements.get('snapshotList').handlers.dragstart({target:firstDragTarget,dataTransfer:transfer,preventDefault(){}});
const emptyTarget={closest:()=>null};elements.get('snapshotList').handlers.drop({target:emptyTarget,dataTransfer:transfer,clientY:999,preventDefault(){}});assert.equal(snapshots.items().at(-1).id,firstBeforeMove.id,'drop in empty rail moves to last saved position');
snapshots.restore(snapshots.items()[0]);assert.equal(cameraSet.yaw,1);assert.equal(restored.joints.length,2);
const article={dataset:{id:snapshots.items()[0].id}},target={closest:selector=>selector==='.snapshotCard'?article:null};
elements.get('snapshotList').handlers.click({target});assert.equal(restored.id,snapshots.items()[0].id);
const deleteTarget={closest:selector=>selector==='.snapshotDelete'?{}:selector==='.snapshotCard'?article:null};
elements.get('snapshotList').handlers.click({target:deleteTarget});assert.equal(snapshots.items().length,1);
const remaining={dataset:{id:snapshots.items()[0].id}},remainingDelete={closest:selector=>selector==='.snapshotDelete'?{}:selector==='.snapshotCard'?remaining:null};
elements.get('snapshotList').handlers.click({target:remainingDelete});assert.equal(snapshots.items().length,0);
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
console.log('PASS: image snapshots persist per model with pose/camera, drag-reorder, restore, delete and selection reset without a default card');
