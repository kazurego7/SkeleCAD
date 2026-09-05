const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const posts=[],workers=[];const events={};
class Worker{constructor(){workers.push(this);}postMessage(data){posts.push(data);}terminate(){this.terminated=true;}}
const window={location:{href:'http://localhost/viewer/'},addEventListener:(type,fn)=>events[type]=fn};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../mesh-cache.js'),'utf8'),{window,Worker,URL,Map,Promise,Date,setTimeout,clearTimeout});
const cache=window.SkeleMeshCache,item=hash=>({path:hash+'.stl',part:{sha256:hash}});
function finish(bytes=72){const p=posts.at(-1);workers.at(-1).onmessage({data:{id:p.id,sha256:p.sha256,mesh:{positions:{byteLength:bytes/2},normals:{byteLength:bytes/2}}}});}
(async()=>{
  const a=cache.load(item('a')),again=cache.load(item('a'));assert.equal(posts.length,1);finish();await Promise.all([a,again]);
  await cache.load(item('a'));assert.equal(posts.length,1,'identical content is not downloaded again');
  cache.prefetch([item('b'),item('c')]);const old=workers.at(-1),fg=cache.load(item('d'));
  assert.equal(posts.at(-1).sha256,'d','foreground interrupts an unrelated prefetch');assert.equal(old.terminated,true);
  old.onerror();assert.notEqual(workers.at(-1).terminated,true,'late errors from a replaced worker are ignored');
  finish();await fg;finish();finish();
  const newer=cache.load(item('new-revision'));assert.equal(posts.at(-1).sha256,'new-revision');finish();await newer;
  const huge=cache.load(item('large'));finish(129*1024*1024);await huge;assert.ok(cache.stats().bytes<=cache.stats().limit,'memory remains bounded');
  const failed=cache.load(item('bad'));workers.at(-1).onmessage({data:{id:posts.at(-1).id,error:'hash mismatch'}});await assert.rejects(failed,/hash mismatch/);
  console.log('PASS: hash-keyed reuse, foreground priority, revision isolation, bounded memory and error eviction');
})().catch(error=>{console.error(error);process.exitCode=1;});
