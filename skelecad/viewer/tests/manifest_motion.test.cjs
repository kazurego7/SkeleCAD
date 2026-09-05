const assert=require('node:assert/strict');
const C=require('../motion-core.js');
const manifest={schema_version:1,parts:['base','linkA','tool'].map(name=>({name,label:name})),
  joints:[{name:'tipJoint',part:'tool',parent:'linkA',center:[4,6,8],direction:[1,2,3]},
          {name:'baseJoint',part:'linkA',parent:'base',center:[1,2,3],direction:[-.3,.95,.1]}]};
const joints=C.manifestJoints(manifest);
for(const j of joints){
  for(const a of j.axes)assert.ok(Math.abs(Math.hypot(...a)-1)<1e-12);
  for(let a=0;a<3;a++)for(let b=a+1;b<3;b++)assert.ok(Math.abs(j.axes[a].reduce((s,v,k)=>s+v*j.axes[b][k],0))<1e-12);
}
const poses=C.poses(joints,{baseJoint:[20,10,30],tipJoint:[10,20,-15]});
assert.deepEqual(C.point(poses.tool,[4,6,8]).map(x=>+x.toFixed(8)),C.point(poses.linkA,[4,6,8]).map(x=>+x.toFixed(8)));
assert.deepEqual(C.point(poses.linkA,[1,2,3]).map(x=>+x.toFixed(8)),[1,2,3]);
const copy=()=>JSON.parse(JSON.stringify(manifest));
let bad=copy();bad.joints[1].parent='tool';assert.throws(()=>C.manifestJoints(bad),/Cyclic/);
bad=copy();bad.joints[0].direction=[0,0,0];assert.throws(()=>C.manifestJoints(bad));
bad=copy();bad.parts.push({name:'orphan'});assert.throws(()=>C.manifestJoints(bad));
bad=copy();bad.joints[1].part='tool';assert.throws(()=>C.manifestJoints(bad));
bad=copy();bad.joints[1].parent='missing';assert.throws(()=>C.manifestJoints(bad));
for(const n of ['__proto__','constructor','prototype']){bad=copy();bad.parts[0].name=n;assert.throws(()=>C.manifestJoints(bad));}
console.log('PASS: arbitrary named part graph, oblique orthonormal axes, attachment invariance and invalid graph rejection');
