const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const posts=[],workers=[];const events={};
class Worker{constructor(){workers.push(this);}postMessage(data){posts.push(data);}terminate(){this.terminated=true;}}
const window={location:{href:'http://localhost/viewer/'},addEventListener:(type,fn)=>events[type]=fn};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../mesh-cache.js'),'utf8'),{window,Worker,URL,Map,Promise,Date,setTimeout,clearTimeout});
const cache=window.SkeleMeshCache,item=hash=>({path:hash+'.stl',part:{sha256:hash}});
function finish(bytes=72){const p=posts.at(-1);workers.at(-1).onmessage({data:{id:p.id,sha256:p.sha256,mesh:{positions:{byteLength:bytes/2},normals:{byteLength:bytes/2}}}});}
(async()=>{
  const a=cache.load(item('a')),again=cache.load(item('a'));assert.equal(posts.length,1);finish();await Promise.all([a,again]);
  assert.equal(posts[0].compact,false,'loopback uses the original STL');
  await cache.load(item('a'));assert.equal(posts.length,1,'identical content is not downloaded again');
  cache.prefetch([item('b'),item('c')]);const old=workers.at(-1),fg=cache.load(item('d'));
  assert.equal(posts.at(-1).sha256,'d','foreground interrupts an unrelated prefetch');assert.equal(old.terminated,true);
  old.onerror();assert.notEqual(workers.at(-1).terminated,true,'late errors from a replaced worker are ignored');
  finish();await fg;finish();finish();
  const newer=cache.load(item('new-revision'));assert.equal(posts.at(-1).sha256,'new-revision');finish();await newer;
  const huge=cache.load(item('large'));finish(129*1024*1024);await huge;assert.ok(cache.stats().bytes<=cache.stats().limit,'memory remains bounded');
  const failed=cache.load(item('bad'));workers.at(-1).onmessage({data:{id:posts.at(-1).id,error:'hash mismatch'}});await assert.rejects(failed,/hash mismatch/);
  const before=posts.length;window.location.href='https://test.ts.net/skelecad/viewer/';
  cache.prefetch([item('remote-prefetch')]);assert.equal(posts.length,before,'remote browsing never starts speculative mesh downloads');
  const remote=cache.load(item('remote-selected'));assert.equal(posts.at(-1).sha256,'remote-selected');assert.equal(posts.at(-1).compact,true,'remote requests compact transport');finish();await remote;
  const exact=cache.loadExact(item('remote-selected'));assert.equal(posts.at(-1).preview,false,'exact collision request does not reuse preview entry');finish();await exact;
  const scoped={path:'../api/jobs/first/files/part.stl',part:{sha256:'shared-part'}};
  const one=cache.load(scoped);finish();await one;
  const scopePosts=posts.length,two=cache.load({...scoped,path:'../api/jobs/second/files/part.stl'});
  assert.equal(posts.length,scopePosts+1,'different models can have different common detail scales for the same part');finish();await two;
  const abandoned=cache.load(item('abandoned')),queued=cache.load(item('abandoned-queued'));
  const abandonedCheck=assert.rejects(abandoned,/変更/),queuedCheck=assert.rejects(queued,/変更/),previousWorker=workers.at(-1);
  cache.retainSources([item('next')]);assert.equal(previousWorker.terminated,true,'selection change cancels obsolete network transfers');
  await Promise.all([abandonedCheck,queuedCheck]);const next=cache.load(item('next'));finish();await next;
  console.log('PASS: hash-keyed reuse, foreground priority, revision isolation, bounded memory and error eviction');
})().catch(error=>{console.error(error);process.exitCode=1;});
