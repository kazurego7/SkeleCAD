const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const nodes=new Map(),uploads=[],deleted=[];let serial=0,downloads=0;
const gl={ARRAY_BUFFER:1,STATIC_DRAW:2,createBuffer:()=>++serial,bindBuffer(){},bufferData:(_,data)=>uploads.push(data),deleteBuffer:id=>deleted.push(id)};
function node(id){if(!nodes.has(id))nodes.set(id,{dataset:{},hidden:true,options:[],handlers:{},getContext:()=>gl,addEventListener(type,fn){this.handlers[type]=fn;}});return nodes.get(id);}
const part=hash=>({name:'core_00',path:'same.stl',sha256:hash,color:'#ffffff'});
let manifest={parts:[part('original')],joints:[]};
const window={addEventListener(){},SkeleCADWorkflow:{manifest:async()=>manifest,modelLoaded(){}},SkeleMeshCache:{load:async item=>{
  downloads++;return {part:item.part,sha256:item.part.sha256,mesh:{positions:new Float32Array([0,0,0,1,0,0,0,1,0]),normals:new Float32Array(9),low:[0,0,0],high:[1,1,0]}};
}}};
const context=vm.createContext({window,document:{getElementById:node},console,performance,setTimeout,clearTimeout,requestAnimationFrame(){},Map,Math,Float32Array,URLSearchParams});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../app.js'),'utf8').replace(/start\(\);\s*$/,''),context);
const load=()=>vm.runInContext("loadModel('job:'+'a'.repeat(32))",context);
(async()=>{
  await load();assert.equal(uploads.length,2);assert.equal(downloads,1);
  await load();assert.equal(uploads.length,2,'returning to a stage reuses GPU buffers');assert.equal(downloads,1);assert.equal(node('gl').dataset.renderCacheHit,'true');
  manifest={parts:[part('new')],joints:[]};await load();assert.equal(uploads.length,4);assert.equal(downloads,2);
  manifest={parts:[part('original')],joints:[]};await load();assert.equal(uploads.length,4);assert.equal(downloads,2);
  assert.equal(node('status').hidden,true,'cache hit does not flash a loading label');
  vm.runInContext(`for(let i=0;i<6;i++){
    const next={positions:{byteLength:20*1024*1024},normals:{byteLength:10*1024*1024},positionBuffer:'p'+i,normalBuffer:'n'+i};
    rememberRender('large'+i,next,[]);mesh=next;trimRenderCache();
    if(renderCacheBytes>renderCacheLimit)throw Error('GPU/CPU cache exceeds bound');
  }`,context);
  assert.ok(deleted.includes('p0')&&!deleted.includes('p5'),'eviction deletes old buffers, never active buffers');
  console.log('PASS: exact revision switching without downloads/uploads, no loading flash, bounded renderer cache and buffer disposal');
})().catch(error=>{console.error(error);process.exitCode=1;});
