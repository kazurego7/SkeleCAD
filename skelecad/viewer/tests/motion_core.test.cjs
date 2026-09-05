const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../motion-core.js');
function close(a,b,tolerance=1e-7){a.forEach((v,k)=>assert.ok(Math.abs(v-b[k])<tolerance,`${a} != ${b}`));}
const pivot=[3,2,1],m=C.rotation([0,0,1],90,pivot);
close(C.point(m,pivot),pivot);close(C.point(m,[4,2,1]),[3,3,1]);close(C.point(C.inverse(m),C.point(m,[8,-5,2])),[8,-5,2]);
const joints=[{name:'hip',part:'leg',center:[0,0,5],axes:[[1,0,0],[0,1,0],[0,0,1]]},{name:'ankle',part:'foot',parent:'leg',center:[0,0,0],axes:[[1,0,0],[0,1,0],[0,0,1]]}];
let pose=C.poses(joints,{hip:[90,0,0],ankle:[0,0,0]});close(C.point(pose.foot,[0,0,0]),[0,5,5]);
pose=C.poses(joints,{hip:[90,0,0],ankle:[0,30,0]});close(C.point(pose.foot,[0,0,0]),[0,5,5]);
const rooted=[joints[1],{...joints[0],parent:'torso'},{name:'body',part:'torso',center:[1,2,3],axes:[[1,0,0],[0,1,0],[0,0,1]]}];
const bent={hip:[23,-17,6],ankle:[-9,12,8]},bodyAngles={...bent,body:[31,-21,14]};
const relative=C.poses(rooted,bent),world=C.poses(rooted,bodyAngles);
for(const name of ['leg','foot'])close(world[name],C.multiply(world.torso,relative[name]));
close(C.point(world.leg,rooted[1].center),C.point(world.torso,rooted[1].center));
close(C.point(world.foot,rooted[0].center),C.point(world.leg,rooted[0].center));
const reordered=C.poses([...rooted].reverse(),bodyAngles);
for(const name of ['torso','leg','foot'])close(world[name],reordered[name]);
assert.throws(()=>C.poses([{...joints[0],parent:'leg'}],{}),/Cyclic/);
console.log('PASS: torso inheritance, bent hip/ankle preserved, joint centres remain attached, unordered hierarchy, no double transform');
function cube(size=2){const a=size/2,v=[[-a,-a,-a],[a,-a,-a],[a,a,-a],[-a,a,-a],[-a,-a,a],[a,-a,a],[a,a,a],[-a,a,a]];const f=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[3,7,6],[3,6,2],[0,4,7],[0,7,3],[1,2,6],[1,6,5]];return new Float32Array(f.flatMap(t=>t.flatMap(i=>v[i])));}
const p=cube(),tree=C.buildBVH(p);assert.equal(C.inside(tree,[0,0,0]),true);assert.equal(C.inside(tree,[2,0,0]),false);assert.equal(C.inside(tree,[1,0,0]),false);
const hollow=C.buildBVH(new Float32Array([...cube(4),...cube(2)]));assert.equal(C.inside(hollow,[0,0,0]),false);assert.equal(C.inside(hollow,[1.5,0,0]),true);
const parts={a:{tree,samples:C.samples(p)},b:{tree,samples:C.samples(p)}};let translated=C.identity();translated[12]=3;assert.equal(C.collide(parts,{b:translated}).pairs.length,0);translated[12]=.6;assert.ok(C.collide(parts,{b:translated}).pairs.length>0);
const selective={
  socket:{tree:C.buildBVH(cube(6)),samples:new Float32Array()},
  ball:{tree:C.buildBVH(cube(6)),samples:new Float32Array([0,0,0,2,0,0])}
};
let filtered=C.collide(selective,{},3000,null,[{a:'ball',b:'socket',owner:'socket',center:[0,0,0],radius:1}]);
assert.equal(filtered.pairs[0].count,1);assert.deepEqual(Array.from(filtered.points),[2,0,0],'the stem-side sample remains visible');
filtered=C.collide(selective,{},3000,null,[{a:'ball',b:'socket',owner:'socket',center:[0,0,0],radius:3}]);
assert.equal(filtered.pairs.length,0,'the intentional spherical mating region is suppressed');
assert.equal(C.pick(p,[{start:0,count:36,part:{name:'a'},low:[-1,-1,-1],high:[1,1,1]}],{},[-4,0,0],[1,0,0]),'a');
console.log('PASS: pivot rotation, inverse transform, foot follows hip, ray picking, cavity parity, selective joint suppression, separated and colliding solids');
if(process.argv.includes('--real')){
  const root=path.join(__dirname,'../..'),cfg=JSON.parse(fs.readFileSync(path.join(root,'config/parameters.json'))),h=cfg.hybrid_new;
  const names=['head','torso','arm_left','arm_right','leg_left','leg_right','foot_left','foot_right','tail'];
  const meshParts={};let start=Date.now();
  for(const name of names){const bytes=fs.readFileSync(path.join(root,h.output_directory,'parts',name+'.stl')),count=bytes.readUInt32LE(80),positions=new Float32Array(count*9);for(let i=0;i<count;i++)for(let k=0;k<9;k++)positions[i*9+k]=bytes.readFloatLE(84+i*50+12+k*4);meshParts[name]={tree:C.buildBVH(positions),samples:C.samples(positions)};}
  console.log('BVH initialization ms',Date.now()-start);start=Date.now();let result=C.collide(meshParts,{});console.log('Neutral collision',result.pairs,'ms',Date.now()-start);assert.equal(result.pairs.length,0);
  start=Date.now();result=C.collide(meshParts,{tail:C.rotation([0,1,0],-35,h.tail_root_center_mm)});console.log('Tail -35deg',result.pairs,'overlay points',result.points.length/3,'ms',Date.now()-start);assert.ok(result.pairs.some(p=>p.a==='tail'||p.b==='tail'));assert.ok(result.points.length>0);
  console.log('PASS: actual nine-part neutral pose clear, excessive tail pitch gives localized collision samples');
  const torsoRotation=C.rotation([1,2,3],37,[0,0,40]);
  const allRotated=Object.fromEntries(names.map(n=>[n,torsoRotation]));
  const movedNeutral=C.collide(meshParts,allRotated);
  assert.equal(movedNeutral.pairs.length,0,'whole assembly rotation must not introduce interference');
  const bentTail=C.rotation([0,1,0],-35,h.tail_root_center_mm);
  const movedCollision=C.collide(meshParts,{...allRotated,tail:C.multiply(torsoRotation,bentTail)});
  assert.deepEqual(movedCollision.pairs,result.pairs,'existing collision retained after root rotation');
  for(let i=0;i<result.points.length;i+=3)close(Array.from(movedCollision.points.slice(i,i+3)),C.point(torsoRotation,Array.from(result.points.slice(i,i+3))),1e-5); // Float32 overlay rounding.
  console.log('PASS: real assembly remains clear under torso rotation; existing collision pairs and red points follow');
  const cache=new Map();C.collide(meshParts,{},3000,cache);
  const jointDefs=h.connections.map(j=>{const part={neck:'head',shoulder_left:'arm_left',shoulder_right:'arm_right',hip_left:'leg_left',hip_right:'leg_right',ankle_left:'foot_left',ankle_right:'foot_right',tail_root:'tail'}[j.name];return {name:j.name,part,center:h[j.center_key],axes:C.jointAxes(j.mouth_direction),parent:part.startsWith('foot_')?part.replace('foot_','leg_'):null};});
  const measurements=[];
  for(const name of ['tail_root','hip_right','shoulder_right','ankle_right']){
    const timings=[];
    for(let n=0;n<16;n++){
      const matrices=C.poses(jointDefs,{[name]:[15+n,10,0]});start=performance.now();
      const cached=C.collide(meshParts,matrices,3000,cache);timings.push(performance.now()-start);
      if(n===0||n===15){const direct=C.collide(meshParts,matrices);assert.deepEqual(cached.pairs,direct.pairs);assert.deepEqual(cached.points,direct.points);}
      if(n>0)assert.ok(cached.cachedPairs>=21,'unchanged pairs must be reused');
    }
    timings.sort((a,b)=>a-b);measurements.push({joint:name,medianMs:+timings[8].toFixed(1),maxMs:+timings.at(-1).toFixed(1)});
  }
  console.log('Full-density incremental collision timings',measurements);
  const reset=C.collide(meshParts,{},3000,cache);assert.equal(reset.pairs.length,0);
  const unchanged=C.collide(meshParts,{},3000,cache);assert.equal(unchanged.evaluatedPairs,0);assert.equal(unchanged.cachedPairs,36);
  console.log('PASS: cached checks exactly match uncached full-density checks, moving feet invalidate with hips, reset clears all collisions');
}
