/* Rigid preview transforms and sampled surface-in-solid collision queries.
   No mesh editing and no printer export. Shared by the viewer, worker and tests. */
(function(root){
  'use strict';
  const identity=()=>[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  function multiply(a,b){const o=new Array(16).fill(0);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o;}
  function point(m,p){return [m[0]*p[0]+m[4]*p[1]+m[8]*p[2]+m[12],m[1]*p[0]+m[5]*p[1]+m[9]*p[2]+m[13],m[2]*p[0]+m[6]*p[1]+m[10]*p[2]+m[14]];}
  function vector(m,p){return [m[0]*p[0]+m[4]*p[1]+m[8]*p[2],m[1]*p[0]+m[5]*p[1]+m[9]*p[2],m[2]*p[0]+m[6]*p[1]+m[10]*p[2]];}
  function inverse(m){const o=[m[0],m[4],m[8],0,m[1],m[5],m[9],0,m[2],m[6],m[10],0,0,0,0,1];const t=vector(o,m.slice(12,15));for(let k=0;k<3;k++)o[12+k]=-t[k];return o;}
  function rotation(axis,degrees,center){
    const len=Math.hypot(...axis),[x,y,z]=axis.map(v=>v/len),a=degrees*Math.PI/180,c=Math.cos(a),s=Math.sin(a),t=1-c;
    const m=[t*x*x+c,t*x*y+s*z,t*x*z-s*y,0,t*x*y-s*z,t*y*y+c,t*y*z+s*x,0,t*x*z+s*y,t*y*z-s*x,t*z*z+c,0,0,0,0,1];
    const p=vector(m,center);for(let k=0;k<3;k++)m[12+k]=center[k]-p[k];return m;
  }
  function jointAxes(direction){
    if(!Array.isArray(direction)||direction.length!==3||!direction.every(Number.isFinite)||Math.hypot(...direction)<1e-9)throw new Error('Invalid joint direction');
    const d=direction.map(x=>x/Math.hypot(...direction));
    // Preserve the accepted cardinal-axis gestures, but orthogonalize oblique joints.
    if(Math.abs(d[1])>1-1e-12)return [[d[1],0,0],[0,0,-d[1]],d];
    if(Math.abs(d[0])>1-1e-12)return [[0,-d[0],0],[0,0,1],d];
    if(Math.abs(d[2])>1-1e-12)return [[1,0,0],[0,1,0],d];
    const ref=Math.abs(d[0])<.8?[1,0,0]:[0,1,0],dot=ref.reduce((s,v,k)=>s+v*d[k],0);
    const raw=ref.map((v,k)=>v-dot*d[k]),a=raw.map(v=>v/Math.hypot(...raw));
    const b=[d[1]*a[2]-d[2]*a[1],d[2]*a[0]-d[0]*a[2],d[0]*a[1]-d[1]*a[0]];
    return [a,b,d];
  }
  function manifestJoints(manifest){
    const safe=n=>typeof n==='string'&&/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/.test(n)&&!['constructor','prototype','__proto__'].includes(n);
    if(manifest?.schema_version!==1||!Array.isArray(manifest.parts)||!Array.isArray(manifest.joints))throw new Error('Invalid model manifest');
    const parts=new Set();
    for(const part of manifest.parts){if(!safe(part.name)||parts.has(part.name))throw new Error('Invalid or duplicate part');parts.add(part.name);}
    const names=new Set(),children=new Set();
    const joints=manifest.joints.map(spec=>{
      if(!safe(spec.name)||names.has(spec.name)||!parts.has(spec.part)||!parts.has(spec.parent)||spec.part===spec.parent||children.has(spec.part))throw new Error('Invalid joint ownership');
      if(!Array.isArray(spec.center)||spec.center.length!==3||!spec.center.every(Number.isFinite))throw new Error('Invalid joint centre');
      names.add(spec.name);children.add(spec.part);
      return {name:spec.name,part:spec.part,parent:spec.parent,center:spec.center.slice(),axes:jointAxes(spec.direction),...(spec.motion_ready===false?{motion_ready:false}:{})};
    });
    if(joints.length){
      if(parts.size!==joints.length+1)throw new Error('Articulated model must have one connected root');
      poses(joints,{}); // Includes cycle detection, independent of manifest order.
    }
    return joints;
  }
  function poses(joints,angles){
    const out={},local={},byPart=new Map(joints.map(j=>[j.part,j])),visiting=new Set();
    for(const j of joints){let m=identity();const a=angles[j.name]||[0,0,0];j.axes.forEach((axis,k)=>{m=multiply(rotation(axis,a[k],j.center),m);});local[j.part]=m;}
    // Resolve parents recursively: torso -> legs -> feet. Definition order
    // must not affect attachment or apply the torso transform twice.
    function resolve(part){
      if(out[part])return out[part];
      if(visiting.has(part))throw new Error('Cyclic part hierarchy');
      visiting.add(part);const j=byPart.get(part),m=local[part]||identity();
      out[part]=j?.parent?multiply(resolve(j.parent),m):m;
      visiting.delete(part);return out[part];
    }
    resolve('torso');for(const j of joints)resolve(j.part);
    return out;
  }
  function transformedBounds(low,high,m){const a=[Infinity,Infinity,Infinity],b=[-Infinity,-Infinity,-Infinity];for(let i=0;i<8;i++){const p=point(m,[0,1,2].map(k=>(i>>k)&1?high[k]:low[k]));for(let k=0;k<3;k++){a[k]=Math.min(a[k],p[k]);b[k]=Math.max(b[k],p[k]);}}return [a,b];}
  function boundsOverlap(a,b){return a[0].every((v,k)=>v<=b[1][k]&&b[0][k]<=a[1][k]);}
  function rayBox(o,d,lo,hi,max=Infinity){let near=0,far=max;for(let k=0;k<3;k++){if(Math.abs(d[k])<1e-12){if(o[k]<lo[k]||o[k]>hi[k])return false;continue;}let a=(lo[k]-o[k])/d[k],b=(hi[k]-o[k])/d[k];if(a>b)[a,b]=[b,a];near=Math.max(near,a);far=Math.min(far,b);if(near>far)return false;}return far>=0;}
  function rayTriangle(p,i,o,d){
    const ax=p[i],ay=p[i+1],az=p[i+2],e1x=p[i+3]-ax,e1y=p[i+4]-ay,e1z=p[i+5]-az,e2x=p[i+6]-ax,e2y=p[i+7]-ay,e2z=p[i+8]-az;
    const hx=d[1]*e2z-d[2]*e2y,hy=d[2]*e2x-d[0]*e2z,hz=d[0]*e2y-d[1]*e2x,det=e1x*hx+e1y*hy+e1z*hz;
    if(Math.abs(det)<1e-12)return Infinity;
    const sx=o[0]-ax,sy=o[1]-ay,sz=o[2]-az,inv=1/det,u=(sx*hx+sy*hy+sz*hz)*inv;if(u<0||u>1)return Infinity;
    const qx=sy*e1z-sz*e1y,qy=sz*e1x-sx*e1z,qz=sx*e1y-sy*e1x,v=(d[0]*qx+d[1]*qy+d[2]*qz)*inv;
    if(v<0||u+v>1)return Infinity;const t=(e2x*qx+e2y*qy+e2z*qz)*inv;return t>=0?t:Infinity;
  }
  function pick(positions,groups,matrices,origin,direction){
    let best=Infinity,hit=null;
    for(const g of groups){if(!g.part)continue;const inv=inverse(matrices[g.part.name]||identity()),o=point(inv,origin),d=vector(inv,direction);
      if(!rayBox(o,d,g.low,g.high,best))continue;
      for(let i=g.start*3,end=(g.start+g.count)*3;i<end;i+=9){const t=rayTriangle(positions,i,o,d);if(t<best){best=t;hit=g.part.name;}}
    }return hit;
  }
  function buildBVH(positions){
    const count=positions.length/9,centers=new Float32Array(count*3),ids=Array.from({length:count},(_,i)=>i);
    for(let i=0;i<count;i++)for(let k=0;k<3;k++)centers[i*3+k]=(positions[i*9+k]+positions[i*9+3+k]+positions[i*9+6+k])/3;
    function build(start,end){
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
      for(let n=start;n<end;n++){const i=ids[n]*9;for(let j=0;j<9;j++){const k=j%3;lo[k]=Math.min(lo[k],positions[i+j]);hi[k]=Math.max(hi[k],positions[i+j]);}}
      const node={lo,hi,start,end};
      if(end-start>24){const size=hi.map((v,k)=>v-lo[k]),axis=size.indexOf(Math.max(...size));const sorted=ids.slice(start,end).sort((a,b)=>centers[a*3+axis]-centers[b*3+axis]);for(let n=0;n<sorted.length;n++)ids[start+n]=sorted[n];const mid=(start+end)>>1;node.left=build(start,mid);node.right=build(mid,end);}
      return node;
    }
    return {positions,ids,root:build(0,count)};
  }
  const rayDirection=[1,.371390676,.197531247];
  function inside(tree,p){
    const root=tree.root;if(p.some((v,k)=>v<root.lo[k]||v>root.hi[k]))return false;
    const hits=[],stack=[root];
    while(stack.length){const n=stack.pop();if(!rayBox(p,rayDirection,n.lo,n.hi))continue;
      if(n.left){stack.push(n.left,n.right);continue;}
      for(let k=n.start;k<n.end;k++){const t=rayTriangle(tree.positions,tree.ids[k]*9,p,rayDirection);if(Number.isFinite(t))hits.push(t);}
    }
    hits.sort((a,b)=>a-b);let count=0,last=-Infinity;
    for(const t of hits){if(t<.01)return false; if(t-last>1e-6){count++;last=t;}}
    return count%2===1;
  }
  function samples(positions,limit=8000){
    const faces=positions.length/9,step=Math.max(1,Math.ceil(faces/(limit/2))),out=[];
    for(let f=0;f<faces;f+=step){const i=f*9;out.push(positions[i],positions[i+1],positions[i+2]);for(let k=0;k<3;k++)out.push((positions[i+k]+positions[i+3+k]+positions[i+6+k])/3);}
    return new Float32Array(out);
  }
  function collide(parts,matrices,maxPoints=3000,cache=null,ignoredRegions=[]){
    const names=Object.keys(parts),bounds={},inverses={},keys={},pairs=[],points=[],ignoredByPair=new Map();let total=0,evaluatedPairs=0,cachedPairs=0;
    for(const region of ignoredRegions){
      if(!region||!names.includes(region.a)||!names.includes(region.b)||!Array.isArray(region.center)||region.center.length!==3||!region.center.every(Number.isFinite)||!Number.isFinite(region.radius)||region.radius<=0)continue;
      const key=[region.a,region.b].sort().join('|'),owner=region.owner||region.a,m=matrices[owner]||identity();
      if(!ignoredByPair.has(key))ignoredByPair.set(key,[]);
      ignoredByPair.get(key).push({center:point(m,region.center),radius2:region.radius*region.radius});
    }
    for(const n of names){const m=matrices[n]||identity();bounds[n]=transformedBounds(parts[n].tree.root.lo,parts[n].tree.root.hi,m);inverses[n]=inverse(m);keys[n]=m.join(',');}
    for(let a=0;a<names.length;a++)for(let b=a+1;b<names.length;b++){
      const na=names[a],nb=names[b],key=[na,nb].sort().join('|'),ignored=ignoredByPair.get(key)||[],ignoreSignature=ignored.map(r=>r.center.join(',')+','+r.radius2).join(';'),signature=keys[na]+'|'+keys[nb]+'|'+maxPoints+'|'+ignoreSignature,previous=cache?.get(key);
      if(previous?.signature===signature){
        cachedPairs++;if(previous.count){pairs.push({a:na,b:nb,count:previous.count});total+=previous.count;points.push(...previous.points);}continue;
      }
      evaluatedPairs++;
      if(!boundsOverlap(bounds[na],bounds[nb])){cache?.set(key,{signature,count:0,points:[]});continue;}
      let count=0;const collected=[];
      for(const [from,to] of [[na,nb],[nb,na]]){
        const s=parts[from].samples,m=matrices[from]||identity(),relative=multiply(inverses[to],m);
        for(let k=0;k<s.length;k+=3){const p=[s[k],s[k+1],s[k+2]],q=point(relative,p);
          if(inside(parts[to].tree,q)){
            const world=point(m,p),intentional=ignored.some(region=>world.reduce((sum,v,i)=>sum+(v-region.center[i])**2,0)<=region.radius2);
            if(!intentional){count++;if(collected.length<maxPoints*3)collected.push(...world);}
          }
        }
      }
      cache?.set(key,{signature,count,points:collected});
      if(count){pairs.push({a:na,b:nb,count});total+=count;points.push(...collected);}
    }
    // Evenly distribute the overlay across all colliding pairs if it is large.
    const out=[],step=Math.max(1,Math.ceil(points.length/(maxPoints*3)));
    for(let k=0;k<points.length;k+=3*step)out.push(points[k],points[k+1],points[k+2]);
    return {pairs,total,points:new Float32Array(out),evaluatedPairs,cachedPairs};
  }
  const api={identity,multiply,point,vector,inverse,rotation,jointAxes,manifestJoints,poses,transformedBounds,boundsOverlap,rayBox,rayTriangle,pick,buildBVH,inside,samples,collide};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SkeleMotion=api;
})(typeof self!=='undefined'?self:this);
