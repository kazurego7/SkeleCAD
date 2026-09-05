"use strict";
(()=>{
  const canvas=document.getElementById('gl'),layer=document.getElementById('partitionMarkers'),toggle=document.getElementById('partitionAdjust'),line=document.getElementById('workflowStatus');
  let active=false,job=null,manifest=null,markers=[],buttons=new Map(),spacingConflicts=[],serial=0,dirty=false,saving=false,awaitingResult=false,saveTimer=null;
  const showMessage=text=>{line.textContent=text;line.hidden=!text;};
  const readyToSave=()=>job&&((['appearance_ready','partition_failed'].includes(job.stage)&&!job.mechanical_revision)||
    (job.mechanical_revision&&['mechanical_review','print_ready','print_failed'].includes(job.stage)&&window.SkeleCADWorkflow?.ensureEditable));
  const partitionFinished=nextJob=>nextJob&&['appearance_ready','partition_failed','failed','interrupted'].includes(nextJob.stage);
  function scheduleSave(delay=0){
    clearTimeout(saveTimer);saveTimer=setTimeout(saveNow,delay);
  }
  function markDirty(message){dirty=true;if(message)showMessage(message);scheduleSave();}
  async function saveNow(){
    clearTimeout(saveTimer);saveTimer=null;if(!dirty||saving||!readyToSave()||!markers.length)return false;
    const selected=markers.map(({name,center,radius_mm,placement_method,symmetry_pair_id})=>({name,center,radius_mm,...(placement_method?{placement_method}:{}),...(symmetry_pair_id?{symmetry_pair_id}:{})}));
    saving=true;dirty=false;showMessage('色分けを自動更新中…');
    try{
      if(job.mechanical_revision)job=await window.SkeleCADWorkflow.ensureEditable(job.id);
      const session=await fetch('../api/session',{cache:'no-store'}).then(r=>r.json());
      const response=await fetch('../api/jobs/'+job.id+'/partition',{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':session.token},body:JSON.stringify({manifest_sha256:job.manifest_sha256,markers:selected})});
      const result=await response.json();if(!response.ok)throw new Error(result.error||'色分けを更新できません');job=result;awaitingResult=!partitionFinished(result);showMessage('色分けを計算中…');return true;
    }catch(error){dirty=true;awaitingResult=false;showMessage(error.message);return false;}
    finally{saving=false;if(dirty&&readyToSave())scheduleSave();}
  }
  function validCandidate(c){return c&&typeof c.name==='string'&&Array.isArray(c.center)&&c.center.length===3&&c.center.every(Number.isFinite)&&Number.isFinite(c.radius_mm);}
  function centerFromHit(hit,radius){
    if(Array.isArray(hit?.solidMidpoint)&&hit.solidMidpoint.length===3&&hit.solidMidpoint.every(Number.isFinite))return hit.solidMidpoint.slice();
    const direction=Array.isArray(hit?.rayDirection)&&hit.rayDirection.length===3&&hit.rayDirection.every(Number.isFinite)?hit.rayDirection:null;
    if(!direction)return hit.point.slice();
    return hit.point.map((v,k)=>v+direction[k]*radius);
  }
  function visualRadius(){
    const controls=manifest?.partition_controls||{},diameter=Number(controls.joint_ball_diameter_mm);
    return Number.isFinite(diameter)&&diameter>0?diameter/2:(Number(controls.default_marker_radius_mm)||6)/2;
  }
  const newPairId=()=>`pair_${Date.now().toString(36)}${(++serial).toString(36)}`;
  const distance=(a,b)=>Math.hypot(...a.map((v,k)=>v-b[k]));
  function failedMarkerLocations(value=job){
    const locations=value?.background?.failed_marker_locations||value?.failed_marker_locations;
    return Array.isArray(locations)?locations.filter(item=>Array.isArray(item?.center)&&item.center.length===3&&item.center.every(Number.isFinite)):[];
  }
  function markerNumbers(){
    const result=new Map(),pairs=new Map();let next=0;
    for(const marker of markers){
      const pairId=marker.symmetry_pair_id;
      if(pairId&&pairs.has(pairId)){result.set(marker,pairs.get(pairId));continue;}
      const number=++next;result.set(marker,number);if(pairId)pairs.set(pairId,number);
    }
    return result;
  }
  function failedMarkers(){
    const locations=failedMarkerLocations(),result=new Set();
    for(const marker of markers)if(locations.some(location=>(location.symmetry_pair_id&&marker.symmetry_pair_id===location.symmetry_pair_id)||distance(marker.center,location.center)<1e-4))result.add(marker);
    return result;
  }
  function markPair(first,second){
    const pairId=first.symmetry_pair_id||second.symmetry_pair_id||newPairId();
    first.symmetry_pair_id=pairId;second.symmetry_pair_id=pairId;first.isMidline=false;second.isMidline=false;
  }
  function removeMarker(marker){
    markers=marker.symmetry_pair_id?markers.filter(m=>m.symmetry_pair_id!==marker.symmetry_pair_id):markers.filter(m=>m!==marker);
    rebuild();markDirty(marker.symmetry_pair_id?'左右対称の2個を削除しました。色分けを自動更新します。':'マーカーを削除しました。色分けを自動更新します。');
  }
  function makeSymmetric(marker,automatic=false){
    if(marker.symmetry_pair_id){
      if(automatic)return false;
      const pairId=marker.symmetry_pair_id;markers=markers.filter(m=>m===marker||m.symmetry_pair_id!==pairId);delete marker.symmetry_pair_id;marker.isMidline=false;marker.placement_method='ray_solid_midpoint_v2';
      rebuild();markDirty('左右対称を解除し、ダブルクリックした側だけ残しました。');return true;
    }
    const reflected=window.SkeleViewer?.reflectPoint(marker.center,marker.radius_mm,manifest?.partition_controls||{},{allowNearPlane:true});
    if(!reflected){showMessage('中心面に近すぎるため、左右対称にできませんでした。');return false;}
    const mirroredCenter=reflected.center;
    let counterpart=markers.find(m=>m!==marker&&distance(m.center,mirroredCenter)<visualRadius());
    if(counterpart?.symmetry_pair_id){showMessage('反対側のマーカーは、すでに別の左右対称ペアに含まれています。');return false;}
    if(!counterpart){
      if(markers.length>=(Number(manifest?.partition_controls?.maximum_markers)||32)){showMessage('マーカー数が上限に達しています。');return false;}
      counterpart={name:'user_'+Date.now().toString(36)+(++serial).toString(36),center:mirroredCenter,radius_mm:marker.radius_mm,source:'user',placement_method:'symmetry_mirror_x_v1'};
      markers.push(counterpart);
    }
    counterpart.center=mirroredCenter.slice();counterpart.radius_mm=marker.radius_mm;counterpart.placement_method='symmetry_mirror_x_v1';
    markPair(marker,counterpart);if(!automatic){rebuild();markDirty('左右対称マーカーにして、反対側にも同じ分割位置を追加しました。');}return true;
  }
  function rebuild(){
    layer.replaceChildren();buttons.clear();
    const numbers=markerNumbers(),failures=failedMarkers();
    for(const [index,marker] of markers.entries()){
      const number=numbers.get(marker),failed=failures.has(marker);
      const button=document.createElement('button');button.type='button';button.className='partitionMarker';
      const markerKind=marker.symmetry_pair_id?'左右対称':marker.isMidline?'中央面':'片側';
      const updateTitle=()=>{button.title=(failed?'加工失敗候補：':'')+'マーカー'+number+'番・'+markerKind+'（ボール径 '+(visualRadius()*2).toFixed(1)+' mm／分割範囲 '+marker.radius_mm.toFixed(1)+' mm）';button.setAttribute('aria-label',button.title);};updateTitle();
      button.textContent=String(number);
      button.dataset.source=marker.source||'automatic';button.dataset.symmetry=String(Boolean(marker.symmetry_pair_id));button.dataset.midline=String(Boolean(marker.isMidline&&!marker.symmetry_pair_id));button.dataset.failed=String(failed);
      button.addEventListener('dblclick',e=>{e.preventDefault();e.stopPropagation();makeSymmetric(marker);});
      button.addEventListener('wheel',e=>{e.preventDefault();e.stopPropagation();const limits=manifest?.partition_controls||{};
        const minimum=Number(limits.minimum_marker_radius_mm)||1,maximum=Number(limits.maximum_marker_radius_mm)||30;
        const radius=Math.min(maximum,Math.max(minimum,marker.radius_mm+(e.deltaY<0?.5:-.5)));
        for(const member of markers)if(member===marker||(marker.symmetry_pair_id&&member.symmetry_pair_id===marker.symmetry_pair_id))member.radius_mm=radius;
        rebuild();markDirty('分割範囲を変更しました。色分けを自動更新します。');},{passive:false});
      button.addEventListener('contextmenu',e=>{e.preventDefault();e.stopPropagation();removeMarker(marker);});
      layer.append(button);buttons.set(marker,button);
    }
    const minimum=Number(manifest?.partition_controls?.minimum_joint_center_spacing_mm);spacingConflicts=[];
    if(Number.isFinite(minimum)&&minimum>0)for(let i=0;i<markers.length;i++)for(let j=i+1;j<markers.length;j++){
      const separation=distance(markers[i].center,markers[j].center);if(separation>=minimum)continue;
      spacingConflicts.push({a:markers[i],b:markers[j],aNumber:numbers.get(markers[i]),bNumber:numbers.get(markers[j]),separation,minimum});buttons.get(markers[i]).dataset.conflict='true';buttons.get(markers[j]).dataset.conflict='true';
    }
    window.SkeleCADWorkflow?.refreshControls?.();
    render();
  }
  function setActive(value){
    active=Boolean(value&&job&&manifest);layer.hidden=!active;canvas.classList.toggle('partitionEditing',active);
    toggle.hidden=true;
    const conflict=spacingConflicts[0];
    showMessage(active?(conflict?`マーカー${conflict.aNumber}番と${conflict.bNumber}番が近すぎます（${conflict.separation.toFixed(1)} mm／必要 ${conflict.minimum.toFixed(1)} mm）。片方を削除し、離れた位置へ追加してください。`:'表示中のマーカーはすべて分割に使います。中央付近は単独、それ以外は自動で左右対称にします。ホイールで範囲調整、右クリックで削除できます。'):'');
    if(dirty&&readyToSave())scheduleSave();
    render();
  }
  function load(nextJob,nextManifest){
    const preserve=job?.id===nextJob?.id&&(dirty||saving||awaitingResult);job=nextJob;manifest=nextManifest;
    if(preserve){if(readyToSave())scheduleSave();render();return;}
    const candidates=(nextManifest?.joint_candidates||[]).filter(validCandidate);
    markers=candidates.map(c=>({name:c.name,center:c.center.slice(),radius_mm:c.radius_mm,source:c.source||'automatic',placement_method:c.placement_method,symmetry_pair_id:c.symmetry_pair_id,isMidline:c.placement_method==='midline_plane_snap_v1',legacySymmetry:c.placement_method==='symmetry_mirror_x_v1'&&!c.symmetry_pair_id,
      needsDepthSnap:(c.source==='user'&&!['ray_solid_midpoint_v2','symmetry_mirror_x_v1','midline_plane_snap_v1'].includes(c.placement_method)),needsMidlineSnap:c.source==='user'&&c.placement_method!=='midline_plane_snap_v1'}));
    serial=markers.filter(m=>m.name.startsWith('user_')).length;dirty=false;rebuild();if(active)setActive(true);
  }
  function render(){
    const step=document.documentElement?.getAttribute?.('data-workflow-step');
    layer.hidden=!active||(step!=null&&step!=='2');
    if(layer.hidden||!window.SkeleViewer)return;
    for(const [marker,button] of buttons){const p=window.SkeleViewer.projectWorld(marker.center);button.hidden=!p;if(p){
      const projectedRadius=millimetres=>Math.max(...[[millimetres,0,0],[0,millimetres,0],[0,0,millimetres]].map(offset=>{const q=window.SkeleViewer.projectWorld(marker.center.map((v,i)=>v+offset[i]));return q?Math.hypot(q.x-p.x,q.y-p.y):0;}));
      const ballRadius=projectedRadius(visualRadius()),rangeRadius=projectedRadius(marker.radius_mm);
      button.style.left=p.x+'px';button.style.top=p.y+'px';button.style.width=Math.max(12,Math.min(72,ballRadius*2))+'px';button.style.height=button.style.width;
      button.style.setProperty('--range-size',Math.max(16,Math.min(128,rangeRadius*2))+'px');button.style.setProperty('--depth',p.depth);}}
  }
  function modelLoaded(){
    if(!active)return;
    let corrected=0,midlineCount=0,symmetryCorrected=0;
    for(const marker of markers){
      if(!marker.needsDepthSnap)continue;marker.needsDepthSnap=false;
      const projected=window.SkeleViewer?.projectWorld(marker.center),hit=projected&&window.SkeleViewer.raycastSurface(projected.x,projected.y,marker.center);
      if(!hit?.solidMidpoint)continue;marker.center=hit.solidMidpoint.slice();marker.placement_method='ray_solid_midpoint_v2';corrected++;
    }
    for(const marker of markers){
      if(marker.source!=='user'||marker.symmetry_pair_id)continue;
      const snapped=window.SkeleViewer?.snapCandidateToMidline(marker.center,marker.radius_mm,manifest?.partition_controls||{});marker.isMidline=Boolean(snapped?.snapped);
      if(!marker.needsMidlineSnap)continue;marker.needsMidlineSnap=false;if(!snapped?.snapped||snapped.shift_mm<1e-4)continue;
      marker.center=snapped.center;marker.placement_method='midline_plane_snap_v1';midlineCount++;
    }
    const pairs=new Map();for(const marker of markers)if(marker.symmetry_pair_id){if(!pairs.has(marker.symmetry_pair_id))pairs.set(marker.symmetry_pair_id,[]);pairs.get(marker.symmetry_pair_id).push(marker);}
    for(const members of pairs.values()){
      if(members.length!==2)continue;
      const mirrored=members.find(marker=>marker.placement_method==='symmetry_mirror_x_v1')||members[1],primary=members.find(marker=>marker!==mirrored);
      const reflected=window.SkeleViewer?.reflectPoint(primary.center,primary.radius_mm,manifest?.partition_controls||{},{allowNearPlane:true});
      if(!reflected||distance(mirrored.center,reflected.center)<1e-4)continue;
      mirrored.center=reflected.center.slice();mirrored.radius_mm=primary.radius_mm;symmetryCorrected++;
    }
    let paired=0;
    for(const marker of markers){
      if(!marker.legacySymmetry||marker.symmetry_pair_id)continue;
      const reflected=window.SkeleViewer?.mirrorCandidate(marker.center,marker.radius_mm,manifest?.partition_controls||{});
      const counterpart=reflected&&markers.find(m=>m!==marker&&!m.symmetry_pair_id&&distance(m.center,reflected.center)<visualRadius());
      if(counterpart){markPair(marker,counterpart);marker.legacySymmetry=false;paired++;}
    }
    let defaultPaired=0;
    for(const marker of [...markers])if(marker.source==='user'&&!marker.symmetry_pair_id&&!marker.isMidline&&makeSymmetric(marker,true))defaultPaired++;
    // Loading or navigating never schedules machining. Persist normalization
    // together with the next explicit marker edit.
    if(corrected||midlineCount||symmetryCorrected||paired||defaultPaired)rebuild();
    else render();
  }
  toggle.addEventListener('click',()=>setActive(!active));
  canvas.addEventListener('dblclick',e=>{
    if(!active||e.button!==0)return;e.preventDefault();e.stopPropagation();const hit=window.SkeleViewer?.raycastSurface(e.clientX,e.clientY);if(!hit)return;
    const radius=Number(manifest?.partition_controls?.default_marker_radius_mm)||6;
    const rawCenter=centerFromHit(hit,visualRadius()),snapped=window.SkeleViewer?.snapCandidateToMidline(rawCenter,radius,manifest?.partition_controls||{}),center=snapped?.center||rawCenter,name='user_'+Date.now().toString(36)+(++serial).toString(36);
    const primary={name,center,radius_mm:radius,source:'user',isMidline:Boolean(snapped?.snapped),placement_method:snapped?.snapped?'midline_plane_snap_v1':'ray_solid_midpoint_v2'};markers.push(primary);
    if(primary.isMidline){rebuild();markDirty('中央マーカーを左右対称面上に追加しました。');}else makeSymmetric(primary);
  });
  function jobUpdated(nextJob){
    if(job?.id!==nextJob?.id)return;
    const failureChanged=JSON.stringify(failedMarkerLocations(job))!==JSON.stringify(failedMarkerLocations(nextJob));
    job=nextJob;if(partitionFinished(nextJob))awaitingResult=false;if(failureChanged)rebuild();
    if(dirty&&readyToSave())scheduleSave();
  }
  const hasPendingChanges=()=>dirty||saving||awaitingResult;
  const hasSpacingConflicts=()=>spacingConflicts.length>0;
  const shouldDeferManifest=nextJob=>active&&job?.id===nextJob?.id&&hasPendingChanges();
  window.SkelePartition={pendingMarkers:()=>hasPendingChanges()?markers.map(m=>({name:m.name,center:m.center.slice(),radius_mm:m.radius_mm,symmetry_pair_id:m.symmetry_pair_id,placement_method:m.placement_method})):null,load,render,modelLoaded,jobUpdated,isActive:()=>active,hasPendingChanges,hasSpacingConflicts,shouldDeferManifest,centerFromHit,begin:()=>setActive(true),end:()=>setActive(false),visualRadius,flush:saveNow};
})();
