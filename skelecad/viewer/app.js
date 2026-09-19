"use strict";
const canvas=document.getElementById('gl'),modelSelect=document.getElementById('modelSelect'),status=document.getElementById('status');
// Snapshots copy the latest WebGL frame into a small JPEG preview.
const gl=canvas.getContext('webgl',{antialias:true,alpha:true,preserveDrawingBuffer:true});
let program,mesh=null,center=[0,0,0],extent=200,distance=310,yaw=-Math.PI/2,pitch=.1,pending=false,loadId=0;
let motion=null,overlayBuffer=null,overlayVersion=-1,roll=0,cameraDragMode='orbit';
let snapshots=null;
let lastMiddleClick=null;
const IDENTITY=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
const pointers=new Map();
const renderCache=new Map(),renderCacheLimit=256*1024*1024;let renderCacheBytes=0;
function renderKey(sources){return sources.every(item=>item.part?.sha256)?JSON.stringify(sources.map(item=>item.part)):null;}
function rememberRender(key,next,items){
  if(!key)return;
  // Count CPU arrays, GPU buffers and retained part arrays, even when shared.
  const bytes=2*(next.positions.byteLength+next.normals.byteLength)+items.reduce((n,item)=>n+item.mesh.positions.byteLength+item.mesh.normals.byteLength,0);
  if(bytes>renderCacheLimit)return;
  next.cached=true;renderCache.set(key,{mesh:next,items,bytes});renderCacheBytes+=bytes;
}
function trimRenderCache(){
  for(const [oldKey,entry] of renderCache){
    if(renderCacheBytes<=renderCacheLimit)break;
    if(entry.mesh===mesh)continue;
    renderCache.delete(oldKey);renderCacheBytes-=entry.bytes;entry.mesh.cached=false;disposeMesh(entry.mesh);
  }
}
const VS='attribute vec3 aPosition;attribute vec3 aNormal;uniform mat4 uMVP;uniform mat4 uModel;uniform float uPointSize;varying float light;void main(){vec3 n=normalize((uModel*vec4(aNormal,0.)).xyz);light=.30+.53*max(dot(n,normalize(vec3(-.35,-.70,.90))),0.)+.20*max(dot(n,normalize(vec3(.75,-.15,.35))),0.);gl_Position=uMVP*vec4(aPosition,1.);gl_PointSize=uPointSize;}';
const FS='precision mediump float;uniform vec3 uColor;uniform float uOpacity;uniform float uOverlay;varying float light;void main(){if(uOverlay>.5){if(length(gl_PointCoord-vec2(.5))>.5)discard;gl_FragColor=vec4(uColor,1.);}else gl_FragColor=vec4(uColor*light,uOpacity);}';
function colorRGB(hex){return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255);}
function combineParts(items){
  const length=items.reduce((sum,item)=>sum+item.mesh.positions.length,0);
  const positions=new Float32Array(length),normals=new Float32Array(length),low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity],groups=[];
  let offset=0;
  for(const item of items){
    positions.set(item.mesh.positions,offset);normals.set(item.mesh.normals,offset);
    groups.push({start:offset/3,count:item.mesh.positions.length/3,part:item.part,low:item.mesh.low,high:item.mesh.high});
    for(let k=0;k<3;k++){low[k]=Math.min(low[k],item.mesh.low[k]);high[k]=Math.max(high[k],item.mesh.high[k]);}
    offset+=item.mesh.positions.length;
  }
  return {positions,normals,low,high,groups};
}
function updatePartState(){
  const parts=(mesh?.groups||[]).map(group=>group.part).filter(Boolean);
  canvas.dataset.partCount=String(parts.length);
  canvas.dataset.colorMode=parts.length?'parts':'bone';
}
function releaseMesh(){
  motion?.clear();
  disposeMesh(mesh);
  mesh=null;
}
function disposeMesh(target){
  if(!target||target.cached)return;
  for(const key of ['positionBuffer','normalBuffer'])if(target[key])gl.deleteBuffer(target[key]);
}
function normalize(v){const n=Math.hypot(...v)||1;return v.map(x=>x/n);}
function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function dot(a,b){return a.reduce((s,x,i)=>s+x*b[i],0);}
function multiply(a,b){
  const out=new Float32Array(16);
  for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)out[c*4+r]+=a[k*4+r]*b[c*4+k];
  return out;
}
function perspective(fov,aspect,near,far){const f=1/Math.tan(fov/2);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0]);}
function lookAt(eye,target,up=[0,0,1]){
  const z=normalize(eye.map((v,i)=>v-target[i])),x=normalize(cross(up,z)),y=cross(z,x);
  return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1]);
}
function parseSTL(buffer){
  if(buffer.byteLength<84)throw new Error('STLファイルが短すぎます');
  const view=new DataView(buffer),count=view.getUint32(80,true);
  if(!count||84+count*50!==buffer.byteLength)throw new Error('バイナリSTLを読み取れません');
  const positions=new Float32Array(count*9),normals=new Float32Array(count*9),low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity];
  for(let f=0;f<count;f++){
    const offset=84+f*50;
    let normal=[0,1,2].map(k=>view.getFloat32(offset+k*4,true));
    for(let j=0;j<3;j++)for(let k=0;k<3;k++){
      const value=view.getFloat32(offset+12+j*12+k*4,true);
      if(!Number.isFinite(value))throw new Error('モデルの座標が不正です');
      positions[f*9+j*3+k]=value;low[k]=Math.min(low[k],value);high[k]=Math.max(high[k],value);
    }
    if(!normal.every(Number.isFinite)||Math.hypot(...normal)<1e-10){
      const a=positions.slice(f*9,f*9+3),b=positions.slice(f*9+3,f*9+6),c=positions.slice(f*9+6,f*9+9);
      normal=normalize(cross(Array.from(b,(v,k)=>v-a[k]),Array.from(c,(v,k)=>v-a[k])));
    }
    for(let j=0;j<3;j++)normals.set(normal,f*9+j*3);
  }
  return {positions,normals,low,high};
}
function compile(type,source){
  const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);
  if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error('描画を準備できません');return shader;
}
function resetView(){
  if(mesh){center=mesh.low.map((v,k)=>(v+mesh.high[k])/2);extent=Math.max(...mesh.high.map((v,k)=>v-mesh.low[k]),.001);}
  yaw=-Math.PI/2;pitch=.1;roll=0;distance=extent*1.55;requestRender();
}
function cameraState(){
  if(!mesh)return null;const fitted=mesh.low.map((v,k)=>(v+mesh.high[k])/2),scale=Math.max(extent,.001);
  return {yaw,pitch,roll,distanceRatio:distance/scale,centerOffset:center.map((v,k)=>(v-fitted[k])/scale)};
}
function restoreCamera(saved){
  if(!mesh||!saved||![saved.yaw,saved.pitch,saved.roll,saved.distanceRatio].every(Number.isFinite)||!Array.isArray(saved.centerOffset)||saved.centerOffset.length!==3||!saved.centerOffset.every(Number.isFinite))return false;
  const fitted=mesh.low.map((v,k)=>(v+mesh.high[k])/2);yaw=saved.yaw;pitch=Math.max(-1.35,Math.min(1.35,saved.pitch));roll=wrapAngle(saved.roll);distance=Math.max(extent*.3,Math.min(extent*8,extent*saved.distanceRatio));center=fitted.map((v,k)=>v+saved.centerOffset[k]*extent);requestRender();return true;
}
function capturePreview(){
  try{
    const out=document.createElement('canvas');out.width=240;out.height=180;const context=out.getContext('2d');context.fillStyle='#292b2f';context.fillRect(0,0,out.width,out.height);
    const sourceWidth=canvas.width||canvas.clientWidth,sourceHeight=canvas.height||canvas.clientHeight;
    if(!sourceWidth||!sourceHeight)return '';
    const scale=Math.min(out.width/sourceWidth,out.height/sourceHeight),width=sourceWidth*scale,height=sourceHeight*scale;
    context.drawImage(canvas,(out.width-width)/2,(out.height-height)/2,width,height);return out.toDataURL('image/jpeg',.72);
  }catch(_){return '';}
}
function zoom(factor){distance=Math.max(extent*.3,Math.min(extent*8,distance*factor));requestRender();}
function requestRender(){if(!pending){pending=true;requestAnimationFrame(render);}}
function cameraParameters(){
  const aspect=Math.max(1,canvas.clientWidth)/Math.max(1,canvas.clientHeight),cp=Math.cos(pitch);
  const eye=[center[0]+distance*cp*Math.cos(yaw),center[1]+distance*cp*Math.sin(yaw),center[2]+distance*Math.sin(pitch)];
  const forward=normalize(center.map((v,k)=>v-eye[k])),right=normalize(cross(forward,[0,0,1])),baseUp=cross(right,forward);
  const up=baseUp.map((v,k)=>v*Math.cos(roll)+right[k]*Math.sin(roll));
  return {center,eye,up,aspect,fov:2*Math.atan(Math.tan(Math.PI/8)/Math.min(1,aspect))};
}
function cameraRay(clientX,clientY){
  const camera=cameraParameters(),rect=canvas.getBoundingClientRect(),nx=2*(clientX-rect.left)/rect.width-1,ny=1-2*(clientY-rect.top)/rect.height;
  const forward=normalize(camera.center.map((v,k)=>v-camera.eye[k])),right=normalize(cross(forward,camera.up)),up=cross(right,forward),t=Math.tan(camera.fov/2);
  return {origin:camera.eye,direction:normalize(forward.map((v,k)=>v+nx*t*camera.aspect*right[k]+ny*t*up[k]))};
}
function raycastSurface(clientX,clientY,referencePoint=null){
  if(!mesh)return null;const ray=cameraRay(clientX,clientY),hits=[],tree=mesh.raycastTree||(mesh.raycastTree=SkeleMotion.buildBVH(mesh.positions)),stack=[tree.root];
  while(stack.length){const node=stack.pop();if(!SkeleMotion.rayBox(ray.origin,ray.direction,node.lo,node.hi))continue;
    if(node.left){stack.push(node.left,node.right);continue;}
    for(let k=node.start;k<node.end;k++){const index=tree.ids[k]*9,t=SkeleMotion.rayTriangle(mesh.positions,index,ray.origin,ray.direction);if(Number.isFinite(t))hits.push({t,index});}}
  if(!hits.length)return null;hits.sort((a,b)=>a.t-b.t);
  const tolerance=Math.max(1e-5,extent*1e-6),unique=[];
  for(const hit of hits)if(!unique.length||hit.t-unique.at(-1).t>tolerance)unique.push(hit);
  const segments=[];for(let i=0;i+1<unique.length;i+=2)segments.push({entry:unique[i],exit:unique[i+1]});
  let segment=segments[0]||{entry:unique[0],exit:null};
  if(segments.length>1&&Array.isArray(referencePoint)&&referencePoint.length===3&&referencePoint.every(Number.isFinite)){
    const distanceToReference=item=>Math.hypot(...ray.origin.map((v,k)=>v+(item.entry.t+item.exit.t)*.5*ray.direction[k]-referencePoint[k]));
    segment=segments.reduce((best,item)=>distanceToReference(item)<distanceToReference(best)?item:best);
  }
  const best=segment.entry.t,index=segment.entry.index,exit=segment.exit?.t;
  const point=ray.origin.map((v,k)=>v+best*ray.direction[k]),normal=normalize(Array.from(mesh.normals.slice(index,index+3)));
  const solidMidpoint=Number.isFinite(exit)?ray.origin.map((v,k)=>v+(best+exit)*.5*ray.direction[k]):null;
  return {point,normal,rayDirection:ray.direction.slice(),solidMidpoint,thickness_mm:Number.isFinite(exit)?exit-best:null};
}
function snapCandidateToMidline(point,radius,controls={}){
  if(!mesh||!Array.isArray(point)||point.length!==3||!point.every(Number.isFinite)||!Number.isFinite(radius)||radius<=0)return null;
  const cfg=controls.midline_snapping||{};if(cfg.enabled===false)return {center:point.slice(),snapped:false,shift_mm:0};
  const axis={x:0,y:1,z:2}[cfg.axis||controls.symmetry_mirroring?.axis||'x'];if(axis===undefined)return null;
  const plane=0,maximumOffset=radius*(Number(cfg.maximum_offset_radius_ratio)||.5),offset=Math.abs(point[axis]-plane);
  if(offset>maximumOffset)return {center:point.slice(),snapped:false,shift_mm:0,axis:['x','y','z'][axis],plane};
  const center=point.slice();center[axis]=plane;return {center,snapped:true,shift_mm:offset,axis:['x','y','z'][axis],plane};
}
function projectWorld(point){
  const camera=cameraParameters(),rect=canvas.getBoundingClientRect(),forward=normalize(camera.center.map((v,k)=>v-camera.eye[k])),right=normalize(cross(forward,camera.up)),up=cross(right,forward);
  const v=point.map((n,k)=>n-camera.eye[k]),depth=dot(v,forward),t=Math.tan(camera.fov/2);if(depth<=0)return null;
  return {x:rect.left+(1+dot(v,right)/(depth*t*camera.aspect))*rect.width/2,y:rect.top+(1-dot(v,up)/(depth*t))*rect.height/2,depth};
}
function reflectPoint(point,radius,controls={},options={}){
  if(!mesh||!Array.isArray(point)||point.length!==3||!point.every(Number.isFinite)||!Number.isFinite(radius)||radius<=0)return null;
  const cfg=controls.symmetry_mirroring||{};if(cfg.enabled===false)return null;
  const axis={x:0,y:1,z:2}[cfg.axis||'x'];if(axis===undefined)return null;
  const plane=0,minimumOffset=radius*(options.allowNearPlane?.05:(Number(cfg.minimum_offset_radius_ratio)||1));
  if(Math.abs(point[axis]-plane)<minimumOffset)return null;
  const mirrored=point.slice();mirrored[axis]=2*plane-mirrored[axis];
  const tree=mesh.raycastTree||(mesh.raycastTree=SkeleMotion.buildBVH(mesh.positions));
  return {center:mirrored,axis:['x','y','z'][axis],plane,inside:SkeleMotion.inside(tree,mirrored)};
}
function mirrorCandidate(point,radius,controls={}){
  const reflected=reflectPoint(point,radius,controls);if(!reflected||!reflected.inside)return null;
  const mirrored=reflected.center,cfg=controls.symmetry_mirroring||{};
  const comparisonRadius=radius*(Number(cfg.comparison_radius_ratio)||1.5),step=Math.max(1,Math.ceil(mesh.positions.length/9/30000));
  function signature(origin){let count=0,total=0;for(let face=0;face<mesh.positions.length/9;face+=step){const i=face*9,c=[0,1,2].map(k=>(mesh.positions[i+k]+mesh.positions[i+3+k]+mesh.positions[i+6+k])/3),d=Math.hypot(...c.map((v,k)=>v-origin[k]));if(d<=comparisonRadius){count++;total+=d;}}return {count,mean:count?total/count:Infinity};}
  const a=signature(point),b=signature(mirrored),minimum=Number(cfg.minimum_sampled_faces)||4;if(a.count<minimum||b.count<minimum)return null;
  const countRatio=Math.min(a.count,b.count)/Math.max(a.count,b.count),meanRatio=Math.min(a.mean,b.mean)/Math.max(a.mean,b.mean);
  if(countRatio<(Number(cfg.face_count_ratio_minimum)||.45)||meanRatio<(Number(cfg.mean_distance_ratio_minimum)||.65))return null;
  return {...reflected,confidence:Math.min(countRatio,meanRatio)};
}
function render(){
  pending=false;if(!program)return;
  const ratio=Math.min(window.devicePixelRatio||1,2),w=Math.max(1,Math.round(canvas.clientWidth*ratio)),h=Math.max(1,Math.round(canvas.clientHeight*ratio));
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
  gl.viewport(0,0,w,h);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  if(!mesh)return;
  const {eye,up,aspect,fov}=cameraParameters(),vp=multiply(perspective(fov,aspect,extent*.001,extent*20),lookAt(eye,center,up));
  gl.uniform1f(gl.getUniformLocation(program,'uOverlay'),0);
  gl.uniform1f(gl.getUniformLocation(program,'uPointSize'),1);
  for(const [name,buffer] of [['aPosition',mesh.positionBuffer],['aNormal',mesh.normalBuffer]]){
    const at=gl.getAttribLocation(program,name);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(at);gl.vertexAttribPointer(at,3,gl.FLOAT,false,0,0);
  }
  const colorLocation=gl.getUniformLocation(program,'uColor');
  const groups=mesh.groups||[{start:0,count:mesh.positions.length/3,part:null}];
  function drawGroup(group,opacity){
    const matrix=motion&&group.part?motion.matrix(group.part.name):IDENTITY;
    gl.uniformMatrix4fv(gl.getUniformLocation(program,'uModel'),false,matrix);
    gl.uniformMatrix4fv(gl.getUniformLocation(program,'uMVP'),false,multiply(vp,matrix));
    const color=group.part?colorRGB(group.part.color):[.88,.76,.58];
    gl.uniform1f(gl.getUniformLocation(program,'uOpacity'),opacity);
    gl.uniform3fv(colorLocation,color);gl.drawArrays(gl.TRIANGLES,group.start,group.count);
  }
  // Always keep every part opaque, including during part and camera gestures.
  gl.disable(gl.BLEND);gl.depthMask(true);
  for(const group of groups)drawGroup(group,1);
  canvas.dataset.nonSelectedOpacity='1';
  if(motion){
    const overlay=motion.overlay(),at=gl.getAttribLocation(program,'aPosition');
    gl.uniformMatrix4fv(gl.getUniformLocation(program,'uModel'),false,IDENTITY);gl.uniformMatrix4fv(gl.getUniformLocation(program,'uMVP'),false,vp);
    gl.uniform1f(gl.getUniformLocation(program,'uOverlay'),1);gl.disable(gl.DEPTH_TEST);
    if(overlay.points.length){
      overlayBuffer ||= gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,overlayBuffer);
      if(overlay.version!==overlayVersion){gl.bufferData(gl.ARRAY_BUFFER,overlay.points,gl.DYNAMIC_DRAW);overlayVersion=overlay.version;}
      gl.vertexAttribPointer(at,3,gl.FLOAT,false,0,0);gl.uniform3fv(colorLocation,[1,.1,.08]);gl.uniform1f(gl.getUniformLocation(program,'uPointSize'),7*ratio);gl.drawArrays(gl.POINTS,0,overlay.points.length/3);
    }
    gl.enable(gl.DEPTH_TEST);
  }
  canvas.dataset.cameraYaw=yaw.toFixed(3);canvas.dataset.cameraPitch=pitch.toFixed(3);canvas.dataset.cameraRoll=roll.toFixed(3);canvas.dataset.cameraDistance=distance.toFixed(3);
  window.SkelePartition?.render();
}
const motionContinuity=new Map();
async function loadModel(path){
  if(!path){++loadId;window.SkeleMeshCache?.retainSources?.([]);releaseMesh();updatePartState();canvas.dataset.model='';canvas.dataset.loaded='false';status.hidden=true;status.dataset.loading='false';requestRender();return;}
  const started=performance.now(),id=++loadId,preserveView=canvas.dataset.model===path&&Boolean(mesh),previousMesh=mesh,preserveMesh=preserveView&&Boolean(previousMesh);
  status.hidden=true;
  let loadingText='モデルを読み込み中…',completedParts=0;
  const loadingTimer=setTimeout(()=>{if(id===loadId){status.dataset.loading='true';status.hidden=false;status.textContent=loadingText;}},150);
  if(!preserveMesh){canvas.dataset.loaded='false';releaseMesh();updatePartState();requestRender();canvas.dataset.model='';}
  const selected=Array.from(modelSelect.options).find(item=>item.value===path);
  modelSelect.title=selected?.dataset.description||'生成したモデル';
  try{
    let manifest=null,sources=[{path,part:null}];
    if(path.startsWith('job:')){
      manifest=await window.SkeleCADWorkflow.manifest(path.slice(4),()=>id===loadId);
      if(id!==loadId)return;
      if(!manifest){status.hidden=true;return;}
      sources=manifest.parts.map(part=>({path:part.path,part}));
    }
    window.SkeleMeshCache?.retainSources?.(sources);
    loadingText='モデルを読み込み中… 0 / '+sources.length+' 部品';
    if(id===loadId&&!status.hidden)status.textContent=loadingText;
    const key=renderKey(sources),cached=key?renderCache.get(key):null;
    if(cached){renderCache.delete(key);renderCache.set(key,cached);}
    const items=cached?.items||await Promise.all(sources.map(async item=>{
      if(window.SkeleMeshCache)return window.SkeleMeshCache.load(item);
      const response=await fetch(item.path,{cache:'default'});if(!response.ok)throw new Error('読み込みエラー '+response.status);
      const bytes=await response.arrayBuffer();
      const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      if(item.part?.sha256&&sha256!==item.part.sha256)throw new Error('生成データの照合に失敗しました');
      return {part:item.part,mesh:parseSTL(bytes),sha256};
    }).map(promise=>promise.then(item=>{
      if(id===loadId){loadingText='モデルを読み込み中… '+(++completedParts)+' / '+sources.length+' 部品';if(!status.hidden)status.textContent=loadingText;}
      return item;
    })));
    if(id!==loadId)return;
    loadingText='表示を準備中…';if(!status.hidden)status.textContent=loadingText;
    // Keep the current model interactive while the next model/config is fetched.
    const preparedParameters=manifest?.joints?.length?await motion?.prepare?.():null;
    if(id!==loadId)return;
    const next=cached?.mesh||combineParts(items);
    if(!cached){
      for(const [key,data] of [['positionBuffer',next.positions],['normalBuffer',next.normals]]){
        next[key]=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,next[key]);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
      }
      rememberRender(key,next,items);
    }
    const stateKey=path.startsWith('job:')?(window.SkeleCADWorkflow?.stateKey?.(path.slice(4))||path):path;
    const previousPose=motion?.continuity?.();
    if(previousPose&&canvas.dataset.model){
      const previousKey=canvas.dataset.stateKey||canvas.dataset.model;
      motionContinuity.delete(previousKey);motionContinuity.set(previousKey,previousPose);
      if(motionContinuity.size>12)motionContinuity.delete(motionContinuity.keys().next().value);
    }
    if(preserveMesh)disposeMesh(previousMesh);
    mesh=next;trimRenderCache();updatePartState();if(preserveView)requestRender();else resetView();window.SkelePartition?.modelLoaded();window.SkeleCADWorkflow?.modelLoaded?.();status.hidden=true;canvas.dataset.loaded='true';canvas.dataset.model=path;
    canvas.dataset.partHashes=JSON.stringify(items.map(item=>({part:item.part?.name||'single',sha256:item.sha256})));
    canvas.dataset.meshDetail=items.some(item=>item.detail==='preview')?'preview':'full';
    canvas.dataset.stateKey=stateKey;
    motion?.load(path,items,manifest,{parameters:preparedParameters,continuity:motionContinuity.get(stateKey)});
    snapshots?.sync();
    canvas.dataset.loadMilliseconds=(performance.now()-started).toFixed(1);
    canvas.dataset.renderCacheHit=String(Boolean(cached));canvas.dataset.renderCacheBytes=String(renderCacheBytes);
  }catch(error){if(id===loadId){status.hidden=false;status.textContent='モデルを開けませんでした：'+error.message;}}
  finally{clearTimeout(loadingTimer);if(id===loadId)status.dataset.loading='false';}
}
function span(){const [a,b]=[...pointers.values()];return a&&b?Math.hypot(a.x-b.x,a.y-b.y):0;}
const wrapAngle=a=>Math.atan2(Math.sin(a),Math.cos(a));
function pointerAngle(){const [a,b]=[...pointers.values()];return a&&b?Math.atan2(b.y-a.y,b.x-a.x):0;}
function pointerMidpoint(){const [a,b]=[...pointers.values()];return a&&b?[(a.x+b.x)/2,(a.y+b.y)/2]:null;}
function panCamera(dx,dy){
  const camera=cameraParameters(),forward=normalize(camera.center.map((v,k)=>v-camera.eye[k])),right=normalize(cross(forward,camera.up));
  const units=2*distance*Math.tan(camera.fov/2)/Math.max(1,canvas.clientHeight);
  center=center.map((v,k)=>v-dx*units*right[k]+dy*units*camera.up[k]);
}
function screenPoint(x,y){const r=canvas.getBoundingClientRect();return [x-r.left-r.width/2,y-r.top-r.height/2];}
function dragMode(x,y,button=0){
  if(button===1)return 'pan';
  if(window.SkeleMobile?.isActive())return 'orbit';
  const p=screenPoint(x,y),r=canvas.getBoundingClientRect();return Math.hypot(p[0]/(r.width/2),p[1]/(r.height/2))>.72?'roll':'orbit';
}
canvas.addEventListener('pointerdown',e=>{
  if(e.pointerType!=='touch'&&e.button!==0&&e.button!==1)return;
  e.preventDefault();pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,button:e.button});canvas.setPointerCapture(e.pointerId);
  canvas.focus({preventScroll:true});
  if(pointers.size===1){cameraDragMode=dragMode(e.clientX,e.clientY,e.button);if(e.button===0)motion?.pointerDown(e);}
  else {for(const pointer of pointers.values())pointer.multi=true;motion?.pointerEnd();}
  requestRender();
});
canvas.addEventListener('pointermove',e=>{
  const old=pointers.get(e.pointerId);if(!old)return;
  const before=span(),beforeAngle=pointerAngle(),beforeMidpoint=pointerMidpoint();pointers.set(e.pointerId,{...old,x:e.clientX,y:e.clientY});
  if(pointers.size===2){const after=span();if(before>4&&after>4){roll=wrapAngle(roll-wrapAngle(pointerAngle()-beforeAngle));zoom(before/after);}if(window.SkeleMobile?.isActive()){const midpoint=pointerMidpoint();panCamera(midpoint[0]-beforeMidpoint[0],midpoint[1]-beforeMidpoint[1]);requestRender();}}
  else if(pointers.size===1){
    const dx=e.clientX-old.x,dy=e.clientY-old.y;
    if(motion?.pointerMove(dx,dy))return;
    if(cameraDragMode==='pan'){
      panCamera(dx,dy);
    }else if(cameraDragMode==='roll'){
      const a=screenPoint(old.x,old.y),b=screenPoint(e.clientX,e.clientY);
      if(Math.hypot(...a)>20&&Math.hypot(...b)>20)roll=wrapAngle(roll-wrapAngle(Math.atan2(b[1],b[0])-Math.atan2(a[1],a[0])));
    }else{
      // Keep screen-direction dragging intuitive after the view has been rolled.
      yaw-=(dx*Math.cos(roll)-dy*Math.sin(roll))*.008;
      pitch=Math.max(-1.35,Math.min(1.35,pitch+(dx*Math.sin(roll)+dy*Math.cos(roll))*.008));
    }
    requestRender();
  }
});
for(const event of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(event,e=>{
  const ended=pointers.get(e.pointerId);if(!ended||!pointers.delete(e.pointerId))return;
  if(event==='pointerup'&&ended.button===1&&Math.hypot(ended.x-ended.startX,ended.y-ended.startY)<=4){
    const now=Number.isFinite(e.timeStamp)?e.timeStamp:Date.now();
    if(lastMiddleClick&&now-lastMiddleClick.time<=400&&Math.hypot(ended.x-lastMiddleClick.x,ended.y-lastMiddleClick.y)<=6){resetView();lastMiddleClick=null;}
    else lastMiddleClick={time:now,x:ended.x,y:ended.y};
  }else if(ended.button===1)lastMiddleClick=null;
  if(pointers.size===1){const p=[...pointers.values()][0];cameraDragMode=dragMode(p.x,p.y,p.button);}
  motion?.pointerEnd();requestRender();
});
canvas.addEventListener('auxclick',e=>{if(e.button===1)e.preventDefault();});
canvas.addEventListener('wheel',e=>{
  e.preventDefault();zoom(Math.exp(e.deltaY*.001));
},{passive:false});
window.addEventListener('resize',requestRender);
// Phone rotation and browser chrome can settle after the window resize event.
if(typeof ResizeObserver!=='undefined')new ResizeObserver(requestRender).observe(canvas);
window.visualViewport?.addEventListener('resize',requestRender);
window.addEventListener('orientationchange',()=>{requestRender();setTimeout(requestRender,250);});
function resetDisplay(){
  resetView();
  if(motion?.isActive())motion.restore({joints:motion.joints().map(j=>({...j,angles:[0,0,0]}))});
  snapshots?.clearSelection();requestRender();
}
document.getElementById('resetView').addEventListener('click',resetDisplay);
modelSelect.addEventListener('change',()=>loadModel(modelSelect.value));
function start(){
  try{
    if(!gl)throw new Error('このブラウザではWebGLを利用できません');
    program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,VS));gl.attachShader(program,compile(gl.FRAGMENT_SHADER,FS));gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('描画を開始できません');
    gl.useProgram(program);gl.enable(gl.DEPTH_TEST);gl.enable(gl.CULL_FACE);gl.cullFace(gl.BACK);
    if(typeof createArticulation==='function')motion=createArticulation({canvas,parts:[],mesh:()=>mesh,camera:cameraParameters,normalize,cross,requestRender,onStateChange:()=>snapshots?.sync()});
    if(typeof createPoseSnapshots==='function')snapshots=(typeof createMobilePoseSnapshots==='function'&&window.matchMedia?.('(max-width: 760px), (max-width: 1024px) and (pointer: coarse), (max-width: 1024px) and (max-height: 500px)').matches?createMobilePoseSnapshots:createPoseSnapshots)({canvas,motion:()=>motion,model:()=>canvas.dataset.stateKey||canvas.dataset.model||modelSelect.value,unscopedModel:()=>canvas.dataset.model,camera:cameraState,setCamera:restoreCamera,resetView,capture:capturePreview,requestRender});
    requestRender();
  }catch(error){status.dataset.loading='false';status.hidden=false;status.textContent=error.message;}
}
window.SkeleViewer={projectWorld,raycastSurface,snapCandidateToMidline,reflectPoint,mirrorCandidate,requestRender,capturePreview};
start();
