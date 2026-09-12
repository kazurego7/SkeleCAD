'use strict';
function createArticulation(api){
  const C=SkeleMotion,canvas=api.canvas,result=document.getElementById('collisionResult'),status=document.getElementById('status'),selectionInfo=document.getElementById('selectionInfo'),twistGuide=document.getElementById('twistGuide');
  const labels=Object.fromEntries(api.parts.map(p=>[p.name,p.label]));
  let joints=[],angles={},displayPose={},matrices={},selected='',selectedPart='',worker=null,ready=false,active=false,failed=false,token=0,sequence=0;
  let inFlight=null,queued=null,dragging=false,twisting=false,marks=new Float32Array(),marksVersion=0,updates=0;
  let circleGesture=null;
  let parked=null,workerKey=null,previewOnly=false,precisionPending=false;
  function clearMarks(){marks=new Float32Array();marksVersion++;result.hidden=true;result.textContent='';canvas.dataset.collisionPairCount='0';}
  function updateSelection(){
    selectionInfo.hidden=!active||!selectedPart;
    const a=displayPose[selected]||[0,0,0];
    selectionInfo.textContent=selectionInfo.hidden?'':labels[selectedPart]+(selected?'　上下 '+a[0].toFixed(1)+'°　左右 '+a[1].toFixed(1)+'°　ねじり '+a[2].toFixed(1)+'°':'　固定');
    canvas.dataset.selectedPart=active?selectedPart:'';
    canvas.dataset.selectedAngles=JSON.stringify(a);
    api.onStateChange?.();
  }
  function pump(){
    if(!worker||!ready||inFlight||!queued)return;
    inFlight=queued;queued=null;
    worker.postMessage({type:'check',id:inFlight.id,matrices:inFlight.matrices});
  }
  function changed(){
    const pose=Object.fromEntries(Object.entries(angles).map(([name,value])=>[name,value.slice()]));
    queued={id:++sequence,pose,matrices:C.poses(joints,pose)};
    canvas.dataset.requestedPose=JSON.stringify(pose);
    // Never debounce until pointer-up: run one check and keep only the newest
    // queued pose. Every finished check is eligible to be displayed.
    if(failed||precisionPending){matrices=queued.matrices;displayPose=pose;updateSelection();canvas.dataset.jointPose=JSON.stringify(pose);queued=null;api.requestRender();return;}
    pump();
  }
  function clear(){
    circleGesture=null;twistGuide.hidden=true;
    token++;
    if(worker&&ready&&!failed&&workerKey){parked?.worker.terminate();parked={worker,key:workerKey};}
    else worker?.terminate();
    worker=null;workerKey=null;ready=false;active=false;failed=false;previewOnly=false;precisionPending=false;dragging=false;twisting=false;inFlight=null;queued=null;
    joints=[];angles={};displayPose={};matrices={};selected='';selectedPart='';updates=0;clearMarks();updateSelection();
    canvas.dataset.motionEnabled='false';canvas.dataset.collisionState='inactive';canvas.dataset.draggingJoint='false';
    for(const name of ['selectedJoint','partGesture','jointPose','requestedPose','collisionRevision','poseRevision','collisionComputeMs','collisionUpdates','collisionUpdatesDuringDrag','collisionLastDragState'])delete canvas.dataset[name];
    api.onStateChange?.();
  }
  async function prepare(){
    const response=await fetch('../config/parameters.json',{cache:'default'});
    if(!response.ok)throw new Error('関節設定を読み込めません');
    return response.json();
  }
  function continuity(){
    if(!active)return null;
    const byPart=new Map(joints.map(j=>[j.part,j]));
    const signature=j=>JSON.stringify([j.name,j.center,j.axes,byPart.has(j.parent)?signature(byPart.get(j.parent)):null]);
    return {selected,entries:Object.fromEntries(joints.map(j=>[j.name,{signature:signature(j),angles:(displayPose[j.name]||[0,0,0]).slice()}]))};
  }
  async function load(path,items,manifest=null,handoff=null){
    clear();if(!manifest?.joints?.length)return;
    const current=token;
    const fail=()=>{
      if(current!==token)return;ready=false;failed=true;worker?.terminate();worker=null;inFlight=null;queued=null;clearMarks();
      canvas.dataset.collisionState='unavailable';status.hidden=false;status.textContent='衝突判定を利用できません。再読み込みしてください。';api.requestRender();
    };
    try{
      const parameters=handoff?.parameters||await prepare();if(current!==token)return;
      const ballDiameter=parameters.joint?.ball_diameter_mm,contactPadding=parameters.printing?.clearance_linear_deflection_mm;
      if(!Number.isFinite(ballDiameter)||ballDiameter<=0||!Number.isFinite(contactPadding)||contactPadding<0)throw new Error('関節寸法が不正です');
      const intentionalContactRadius=ballDiameter/2+contactPadding;
      {
        joints=C.manifestJoints(manifest);previewOnly=manifest.preview_only===true;
        if(items.length!==manifest.parts.length||items.some(item=>!manifest.parts.some(p=>p.name===item.part?.name)))throw new Error('パーツと関節情報が一致しません');
        for(const p of manifest.parts)labels[p.name]=p.label||p.name;
        const first=joints.find(j=>j.motion_ready!==false)||joints[0];selected=first.name;selectedPart=first.part;
      }
      const byPart=new Map(joints.map(j=>[j.part,j]));
      const signature=j=>JSON.stringify([j.name,j.center,j.axes,byPart.has(j.parent)?signature(byPart.get(j.parent)):null]);
      let preserved=0;
      angles=Object.fromEntries(joints.map(j=>{
        const saved=handoff?.continuity?.entries?.[j.name];
        const keep=saved?.signature===signature(j)&&Array.isArray(saved.angles)&&saved.angles.length===3&&saved.angles.every(Number.isFinite);
        if(keep)preserved++;
        return [j.name,keep?saved.angles.slice():[0,0,0]];
      }));
      if(joints.some(j=>j.name===handoff?.continuity?.selected)){
        selected=handoff.continuity.selected;selectedPart=joints.find(j=>j.name===selected).part;
      }
      displayPose=Object.fromEntries(Object.entries(angles).map(([name,value])=>[name,value.slice()]));matrices=C.poses(joints,angles);
      canvas.dataset.preservedJointCount=String(preserved);
      active=true;canvas.dataset.motionEnabled='true';canvas.dataset.selectedJoint=selected;canvas.dataset.jointPose=JSON.stringify(angles);
      updateSelection();api.requestRender();
      if(items.some(item=>item.detail==='preview')){
        // Keep the light display interactive while exact collision geometry arrives.
        // Never declare a low-detail mesh collision-free or ready for review.
        precisionPending=true;canvas.dataset.collisionState='preparing';
        status.hidden=false;status.textContent='軽量表示中 · 衝突判定用の精密形状を読み込み中…';
        items=await Promise.all(items.map(item=>window.SkeleMeshCache.loadExact({path:item.part.path,part:item.part})));
        if(current!==token)return;
        if(items.some(item=>item.detail==='preview'))throw new Error('精密形状を読み込めません');
        precisionPending=false;
      }
      workerKey=items.every(item=>/^[0-9a-f]{64}$/.test(item.sha256||''))?
        JSON.stringify({parts:items.map(item=>[item.part.name,item.sha256]),joints,intentionalContactRadius}):null;
      const reused=Boolean(workerKey&&parked?.key===workerKey);
      worker=reused?parked.worker:new Worker('collision-worker.js?v=3.4.3');
      if(parked&&!reused)parked.worker.terminate();parked=null;
      ready=reused;canvas.dataset.collisionWorkerReused=String(reused);
      canvas.dataset.collisionState='preparing';status.hidden=reused;if(!reused)status.textContent='関節を準備中…';
      const thisWorker=worker;
      const discardParked=()=>{if(parked?.worker===thisWorker){parked.worker.terminate();parked=null;}};
      worker.onerror=()=>{discardParked();fail();};
      worker.onmessage=e=>{
        if(e.data.type==='error')discardParked();
        if(current!==token||failed)return;const data=e.data;
        if(data.type==='ready'){ready=true;pump();return;}
        if(data.type==='error'){fail();return;}
        if(data.type!=='result'||!inFlight||data.id!==inFlight.id)return;
        // Commit tested pose and collision overlay atomically. Keeping them
        // together prevents stale marks and starvation during continuous input.
        matrices=inFlight.matrices;displayPose=inFlight.pose;updateSelection();canvas.dataset.jointPose=JSON.stringify(inFlight.pose);
        canvas.dataset.poseRevision=String(data.id);canvas.dataset.collisionRevision=String(data.id);
        canvas.dataset.collisionComputeMs=Number(data.computeMs||0).toFixed(1);
        canvas.dataset.collisionUpdates=String(++updates);
        canvas.dataset.collisionPairCount=String(data.pairs.length);
        canvas.dataset.collisionState=data.pairs.length?'collision':'clear';
        if(dragging){canvas.dataset.collisionUpdatesDuringDrag=String(1+Number(canvas.dataset.collisionUpdatesDuringDrag||0));canvas.dataset.collisionLastDragState=canvas.dataset.collisionState;}
        marks=data.points;marksVersion++;result.hidden=!data.pairs.length;
        result.textContent=data.pairs.length?'衝突：'+data.pairs.map(p=>labels[p.a]+' ↔ '+labels[p.b]).join(' ／ ')+'（近似）':'';
        status.hidden=true;inFlight=null;api.requestRender();pump();
      };
      const payload=reused?[]:items.map(item=>({name:item.part.name,positions:item.mesh.positions.slice()}));
      // The fitted ball intentionally intersects its own socket. Suppress only
      // that spherical region for the mating pair; stem/anatomy collisions and
      // collisions with every other part remain visible.
      const ignoredRegions=joints.map(j=>({a:j.parent,b:j.part,owner:j.parent,center:j.center,radius:intentionalContactRadius}));
      if(!reused)worker.postMessage({type:'init',parts:payload,ignoredRegions},payload.map(p=>p.positions.buffer));changed();
    }catch(error){fail();}
  }
  function pointerDown(e){
    if(!active||e.altKey||e.button!==0)return false;
    const camera=api.camera(),rect=canvas.getBoundingClientRect(),nx=2*(e.clientX-rect.left)/rect.width-1,ny=1-2*(e.clientY-rect.top)/rect.height;
    const forward=api.normalize(camera.center.map((v,k)=>v-camera.eye[k])),right=api.normalize(api.cross(forward,camera.up||[0,0,1])),up=api.cross(right,forward),t=Math.tan(camera.fov/2);
    const direction=api.normalize(forward.map((v,k)=>v+nx*t*camera.aspect*right[k]+ny*t*up[k]));
    const mesh=api.mesh(),part=C.pick(mesh.positions,mesh.groups,matrices,camera.eye,direction),joint=joints.find(j=>j.part===part);
    if(!part)return false;
    selectedPart=part;selected=joint?joint.name:'';canvas.dataset.selectedJoint=selected;updateSelection();api.requestRender();
    if(!joint||joint.motion_ready===false)return false;
    dragging=true;twisting=Boolean(e.shiftKey);circleGesture=null;
    // A screen-space ring is only a gesture guide, not a physical joint outline.
    const group=mesh.groups?.find(g=>g.part?.name===part);
    if(group){
      const projected=[];
      for(let i=0;i<8;i++){
        const p=C.point(matrices[part]||C.identity(),[0,1,2].map(k=>(i>>k)&1?group.high[k]:group.low[k]));
        const v=p.map((n,k)=>n-camera.eye[k]),dot=(a,b)=>a.reduce((s,n,k)=>s+n*b[k],0),depth=dot(v,forward);
        if(depth<=0)continue;
        projected.push([rect.left+(1+dot(v,right)/(depth*t*camera.aspect))*rect.width/2,rect.top+(1-dot(v,up)/(depth*t))*rect.height/2]);
      }
      if(projected.length===8){
        const lo=[0,1].map(k=>Math.min(...projected.map(p=>p[k]))),hi=[0,1].map(k=>Math.max(...projected.map(p=>p[k])));
        const cx=(lo[0]+hi[0])/2,cy=(lo[1]+hi[1])/2;
        // Keep the bend region inside the short dimension so slender parts
        // still have a reachable outer region for twisting, including on phones.
        const radius=Math.max(6,Math.min(Math.min(hi[0]-lo[0],hi[1]-lo[1])*.28,Math.min(rect.width,rect.height)*.08));
        const circular=!twisting&&Math.hypot(e.clientX-cx,e.clientY-cy)>=radius;
        const worldAxis=C.vector(matrices[joint.parent]||C.identity(),joint.axes[2]);
        const facing=worldAxis.reduce((s,v,k)=>s+v*forward[k],0);
        circleGesture={cx,cy,x:e.clientX,y:e.clientY,circular,twistAngle:angles[selected][2],sign:facing<-.001?-1:1};
        twistGuide.style.left=cx+'px';twistGuide.style.top=cy+'px';twistGuide.style.width=radius*2+'px';twistGuide.style.height=radius*2+'px';
        twistGuide.dataset.mode=circular||twisting?'twist':'bend';twistGuide.hidden=false;
      }
    }
    canvas.dataset.partGesture=twisting||circleGesture?.circular?'twist':'bend';
    canvas.dataset.draggingJoint='true';return true;
  }
  const limit=n=>Math.round(Math.max(-60,Math.min(60,n))*10)/10;
  function pointerMove(dx,dy){
    if(!dragging)return false;
    if(circleGesture?.circular){
      const g=circleGesture,ax=g.x-g.cx,ay=g.y-g.cy,bx=ax+dx,by=ay+dy;
      if(Math.hypot(ax,ay)>8&&Math.hypot(bx,by)>8){const delta=Math.atan2(by,bx)-Math.atan2(ay,ax);g.twistAngle=Math.max(-60,Math.min(60,g.twistAngle+g.sign*Math.atan2(Math.sin(delta),Math.cos(delta))*180/Math.PI));angles[selected][2]=limit(g.twistAngle);}
    }
    else if(twisting)angles[selected][2]=limit(angles[selected][2]+dx*.4);
    else{angles[selected][0]=limit(angles[selected][0]-dy*.4);angles[selected][1]=limit(angles[selected][1]+dx*.4);}
    if(circleGesture){circleGesture.x+=dx;circleGesture.y+=dy;}
    changed();return true;
  }
  function pointerEnd(){dragging=false;circleGesture=null;twistGuide.hidden=true;canvas.dataset.draggingJoint='false';canvas.dataset.partGesture='';pump();}
  function jointState(){
    return joints.map(j=>({name:j.name,part:j.part,parent:j.parent,center:j.center.slice(),direction:j.axes[2].slice()}));
  }
  function restore(snapshot){
    if(!active||!snapshot||typeof snapshot!=='object')return {restored:0,total:joints.length};
    const saved=Array.isArray(snapshot.joints)?snapshot.joints:[],used=new Set();let restored=0;
    function validAngles(value){return Array.isArray(value)&&value.length===3&&value.every(Number.isFinite);}
    function candidateFor(joint){
      let index=saved.findIndex((item,k)=>!used.has(k)&&item.name===joint.name&&validAngles(item.angles));
      if(index<0)index=saved.findIndex((item,k)=>!used.has(k)&&item.part===joint.part&&validAngles(item.angles));
      if(index<0){
        const compatible=saved.map((item,k)=>({item,k})).filter(({item,k})=>!used.has(k)&&item.parent===joint.parent&&validAngles(item.angles)&&Array.isArray(item.center)&&item.center.length===3);
        compatible.sort((a,b)=>Math.hypot(...a.item.center.map((v,k)=>v-joint.center[k]))-Math.hypot(...b.item.center.map((v,k)=>v-joint.center[k])));
        if(compatible.length)index=compatible[0].k;
      }
      return index;
    }
    for(const joint of joints){
      if(joint.motion_ready===false)continue;
      const index=candidateFor(joint);
      if(index>=0){angles[joint.name]=saved[index].angles.map(limit);used.add(index);restored++;}
      else angles[joint.name]=[0,0,0];
    }
    if(!joints.some(j=>j.name===selected)){selected=joints[0]?.name||'';selectedPart=joints[0]?.part||'';canvas.dataset.selectedJoint=selected;}changed();
    return {restored,total:joints.length};
  }
  canvas.addEventListener('keydown',e=>{
    if(!active)return;
    if(e.key==='Escape'){for(const j of joints)if(j.motion_ready!==false)angles[j.name]=[0,0,0];}
    else if(e.key==='Home'&&selected&&joints.find(j=>j.name===selected)?.motion_ready!==false){angles[selected]=[0,0,0];}
    else if(selected&&joints.find(j=>j.name===selected)?.motion_ready!==false&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){
      const k=e.shiftKey?2:(e.key==='ArrowUp'||e.key==='ArrowDown'?0:1),delta=e.key==='ArrowUp'||e.key==='ArrowRight'?1:-1;angles[selected][k]=limit(angles[selected][k]+delta);
    }else return;
    e.preventDefault();changed();
  });
  return {load,prepare,continuity,clear,pointerDown,pointerMove,pointerEnd,restore,isActive:()=>active,joints:jointState,selectedPart:()=>active?selectedPart:null,matrix:name=>matrices[name]||C.identity(),overlay:()=>({points:marks,version:marksVersion}),
    reviewState:()=>({ready:active&&ready&&!previewOnly&&!failed&&!queued&&!inFlight&&updates>0,collision:canvas.dataset.collisionState,
                     pose:JSON.parse(JSON.stringify(displayPose)),revision:canvas.dataset.poseRevision||null})};
}
