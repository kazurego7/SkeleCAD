const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');

const nodes=new Map(),requests=[],timers=new Map();let timerId=0;
function baseNode(id=''){
  return {id,hidden:true,disabled:false,dataset:{},handlers:{},children:[],style:{setProperty(name,value){this[name]=value;}},classList:{toggle(){}},
    addEventListener(type,fn){this.handlers[type]=fn;},setAttribute(name,value){this[name]=value;},append(child){this.children.push(child);},replaceChildren(){this.children=[];}};
}
function node(id){if(!nodes.has(id))nodes.set(id,baseNode(id));return nodes.get(id);}
const viewer={
  projectWorld(center){return {x:center[0]+100,y:center[1]+100,depth:0};},
  snapCandidateToMidline(center,radius){const snapped=Math.abs(center[0])<=radius*.5,next=center.slice();if(snapped)next[0]=0;return {center:next,snapped,shift_mm:snapped?Math.abs(center[0]):0};},
  reflectPoint(center,radius,controls,options){return Math.abs(center[0])<(options?.allowNearPlane?.05*radius:1)?null:{center:[-center[0],center[1],center[2]],axis:'x',inside:false};},
  mirrorCandidate(center){return Math.abs(center[0])<1?null:{center:[-center[0],center[1],center[2]],axis:'x'};},
  raycastSurface(){return null;}
};
const context=vm.createContext({console,Math,Date,Map,Array,Number,setTimeout(fn){timers.set(++timerId,fn);return timerId;},clearTimeout(id){timers.delete(id);},
  document:{getElementById:node,createElement:()=>baseNode()},
  window:{SkeleViewer:viewer},
  fetch:async(url,options={})=>{requests.push({url,options});const match=url.match(/jobs\/([a-f0-9]{32})\/partition$/);return {ok:true,json:async()=>url.endsWith('/session')?{token:'token'}:{id:match?.[1],stage:'partitioning',message:'queued'}};}
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../partition-ui.js'),'utf8'),context);
const api=context.window.SkelePartition;
const manifest={partition_controls:{joint_ball_diameter_mm:6,default_marker_radius_mm:6,maximum_markers:32},joint_candidates:[
  {name:'candidate_01',center:[5,0,0],radius_mm:6,source:'automatic',classification:'two_part_junction'}
]};
api.load({id:'a'.repeat(32),stage:'appearance_ready',manifest_sha256:'hash'},manifest);api.begin();
assert.equal(node('partitionMarkers').children.length,1);
const ordinary=node('partitionMarkers').children[0];
assert.equal(ordinary.handlers.click,undefined,'a marker has no active/inactive toggle');
ordinary.handlers.dblclick({preventDefault(){},stopPropagation(){}});
assert.equal(node('partitionMarkers').children.length,2,'double-click creates the reflected marker');
assert.ok(node('partitionMarkers').children.every(button=>button.dataset.symmetry==='true'),'both pair members use the symmetry colour state');
assert.equal(node('partitionMarkers').children[0].textContent,node('partitionMarkers').children[1].textContent,'both pair members share one visible number');
node('partitionMarkers').children[0].handlers.dblclick({preventDefault(){},stopPropagation(){}});
assert.equal(node('partitionMarkers').children.length,1,'double-clicking a pair keeps only the clicked member');
assert.equal(node('partitionMarkers').children[0].dataset.symmetry,'false');
node('partitionMarkers').children[0].handlers.dblclick({preventDefault(){},stopPropagation(){}});
assert.equal(node('partitionMarkers').children.length,2,'the remaining marker can be paired again');
node('partitionMarkers').children[0].handlers.contextmenu({preventDefault(){},stopPropagation(){}});
assert.equal(node('partitionMarkers').children.length,0,'deleting either member deletes the pair');

manifest.joint_candidates=[
  {name:'candidate_01',center:[5,0,0],radius_mm:6,source:'automatic',classification:'rejected_not_boundary'},
  {name:'candidate_02',center:[0,5,0],radius_mm:6,source:'automatic',classification:'rounded_terminal'}
];
api.load({id:'b'.repeat(32),stage:'appearance_ready',manifest_sha256:'hash'},manifest);api.begin();
node('partitionMarkers').children[0].handlers.wheel({deltaY:-1,preventDefault(){},stopPropagation(){}});
(async()=>{
  await api.flush();
  assert.equal(api.hasPendingChanges(),true,'the submitted revision stays pending until its result arrives');
  api.jobUpdated({id:'b'.repeat(32),stage:'appearance_ready',manifest_sha256:'result-1'});
  assert.equal(api.hasPendingChanges(),false,'the matching completed result clears the pending state');
  const posted=requests.find(request=>request.url.endsWith('/partition'));
  const markers=JSON.parse(posted.options.body).markers;
  assert.equal(markers.length,2,'every visible marker is submitted regardless of former classification');
  assert.equal(markers.some(marker=>'enabled' in marker),false);
  manifest.joint_candidates=[{name:'user_ab12',center:[5,0,0],radius_mm:6,source:'user',placement_method:'ray_solid_midpoint_v2'}];
  api.load({id:'c'.repeat(32),stage:'appearance_ready',manifest_sha256:'hash'},manifest);api.modelLoaded();
  assert.equal(node('partitionMarkers').children.length,2,'a loaded lateral user marker becomes a symmetric pair by default');
  assert.ok(node('partitionMarkers').children.every(button=>button.dataset.symmetry==='true'));
  manifest.joint_candidates=[{name:'user_cd34',center:[.5,0,0],radius_mm:6,source:'user',placement_method:'ray_solid_midpoint_v2'}];
  api.load({id:'a'.repeat(32),stage:'appearance_ready',manifest_sha256:'hash'},manifest);api.modelLoaded();
  assert.equal(node('partitionMarkers').children.length,1,'a marker snapped to the midline stays single');
  assert.equal(node('partitionMarkers').children[0].dataset.midline,'true','an original midline marker has its own colour state');
  assert.match(node('partitionMarkers').children[0].title,/中央面/);
  assert.equal(node('partitionApply').handlers.click,undefined,'there is no manual preview-update action');

  manifest.joint_candidates=[{name:'candidate_race',center:[5,0,0],radius_mm:6,source:'automatic'}];
  api.load({id:'d'.repeat(32),stage:'appearance_ready',manifest_sha256:'race-0'},manifest);api.begin();
  node('partitionMarkers').children[0].handlers.wheel({deltaY:-1,preventDefault(){},stopPropagation(){}});await api.flush();
  node('partitionMarkers').children[0].handlers.wheel({deltaY:1,preventDefault(){},stopPropagation(){}});
  api.end();
  const pendingRadius=node('partitionMarkers').children[0].title;
  api.load({id:'d'.repeat(32),stage:'partitioning',manifest_sha256:'race-0'},manifest);
  assert.equal(node('partitionMarkers').children[0].title,pendingRadius,'returning preserves unsaved edits while inactive');
  api.jobUpdated({id:'d'.repeat(32),stage:'appearance_ready',manifest_sha256:'race-1'});
  assert.equal(api.hasPendingChanges(),true,'an intermediate result is deferred while a newer local marker operation exists');
  const countBefore=requests.filter(r=>r.url.endsWith('/partition')).length;
  await api.flush();
  assert.equal(requests.filter(r=>r.url.endsWith('/partition')).length,countBefore+1,'pending edits continue saving after leaving partition');
  api.begin();
  assert.equal(api.shouldDeferManifest({id:'d'.repeat(32)}),true,'the newest submitted operation remains protected while its worker runs');
  api.jobUpdated({id:'d'.repeat(32),stage:'appearance_ready',manifest_sha256:'race-2'});
  assert.equal(api.shouldDeferManifest({id:'d'.repeat(32)}),false,'only the newest completed marker state becomes displayable');

  manifest.joint_candidates=[
    {name:'new_before',center:[0,9,0],radius_mm:6,source:'automatic'},
    {name:'pair_left',center:[5,0,0],radius_mm:6,source:'user',symmetry_pair_id:'pair_failure'},
    {name:'pair_right',center:[-5,0,0],radius_mm:6,source:'user',symmetry_pair_id:'pair_failure'},
    {name:'ordinary_after',center:[0,-9,0],radius_mm:6,source:'automatic'}
  ];
  api.load({id:'f'.repeat(32),stage:'machining_failed',manifest_sha256:'failure',failed_marker_locations:[{center:[5,0,0],symmetry_pair_id:'pair_failure'}]},manifest);
  const failureButtons=node('partitionMarkers').children;
  assert.equal(failureButtons[1].textContent,failureButtons[2].textContent,'a failed bilateral pair keeps one shared number after insertion before it');
  assert.equal(failureButtons[1].dataset.failed,'true');assert.equal(failureButtons[2].dataset.failed,'true','both sides of a failed pair are highlighted');
  assert.equal(failureButtons[0].dataset.failed,'false');assert.equal(failureButtons[3].dataset.failed,'false','other display numbers do not inherit the failure');
  failureButtons[1].handlers.contextmenu({preventDefault(){},stopPropagation(){}});
  assert.ok(node('partitionMarkers').children.every(button=>button.dataset.failed==='false'),'deleting the failed pair never moves the failure highlight to another marker');

  manifest.partition_controls.minimum_joint_center_spacing_mm=10.15;
  manifest.joint_candidates=[{name:'candidate_close_a',center:[0,0,0],radius_mm:6,source:'automatic'},
    {name:'candidate_close_b',center:[6,0,0],radius_mm:6,source:'automatic'}];
  api.load({id:'e'.repeat(32),stage:'appearance_ready',manifest_sha256:'spacing'},manifest);api.begin();
  assert.equal(api.hasSpacingConflicts(),true,'socket-envelope spacing conflicts are exposed to workflow controls');
  assert.ok(node('partitionMarkers').children.every(button=>button.dataset.conflict==='true'),'both conflicting markers use the warning colour');
  assert.match(node('workflowStatus').textContent,/6\.0 mm.*10\.2 mm/);
  console.log('PASS: operation-driven background save, all visible markers active, default lateral pairing, midline singletons, pair toggle/colour and linked deletion');
  console.log('PASS: intermediate partition revisions stay hidden until the latest marker operation completes');
  console.log('PASS: failure identity survives renumbering and bilateral markers share one failed number');
  console.log('PASS: underspaced joint markers are visibly blocked before machining');
})().catch(error=>{console.error(error);process.exitCode=1;});
