const assert=require('node:assert/strict');
const {createSnapshotSync}=require('../snapshot-sync.js');
const clone=x=>JSON.parse(JSON.stringify(x));
const key='skelecad.poseSnapshots.v1';
const pendingKey='skelecad.poseSnapshots.unsent';
let server={initialized:false,revision:0,items:[]},offline=false,posts=0;
let waitGet=null,waitPost=null;
const snapshot=(id,model='model-a')=>({id,model,schema:1,joints:[{angles:[1,2,3]}],camera:{yaw:2},image:'data:image/jpeg;base64,YQ==',order:0});
function client(initial){
  const memory=new Map([[key,JSON.stringify(initial)]]),state={items:initial,editing:false,notices:[]};
  const storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
  const sync=createSnapshotSync({storage,isEditing:()=>state.editing,onChange:v=>state.items=v,notify:v=>state.notices.push(v),async request(path,init){
    if(offline)throw Error('offline');
    if(path==='session')return {token:'test'};
    if(!init){const value=clone(server);if(waitGet)await waitGet;return value;}
    posts++;if(waitPost)await waitPost;
    const data=JSON.parse(init.body);
    if(data.revision!==server.revision)throw Error('conflict');
    server={initialized:true,revision:server.revision+1,items:data.items};return clone(server);
  }});
  return {...sync,state,memory};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  // Migration is performed outside the app; this fixture is already shared.
  server={revision:1,items:[snapshot('phone-1'),snapshot('phone-2','model-b')]};
  const desktop=client([snapshot('desktop-old')]),phone=client([]);
  assert.equal(desktop.write([]),false);assert.equal(posts,0);
  await desktop.refresh();await phone.refresh();
  assert.deepEqual(desktop.state.items,phone.state.items);
  assert.equal(JSON.parse(desktop.memory.get(key))[0].id,'desktop-old','legacy data stays untouched');
  const updated=[snapshot('new'),...phone.state.items];
  assert.equal(phone.write(updated),true);assert.equal(phone.write([]),false);await settle();
  await desktop.refresh();assert.deepEqual(desktop.state.items,updated);
  const stale=client([],false);await stale.refresh();
  assert.equal(desktop.write([snapshot('other-device')]),true);await settle();
  assert.equal(stale.write([snapshot('stale-edit')]),true);await settle();
  assert.equal(server.items[0].id,'other-device');assert.match(stale.state.notices.at(-1),/conflict/);
  assert.equal(JSON.parse(stale.memory.get(pendingKey))[0].id,'stale-edit');
  await stale.refresh();assert.equal(stale.state.items[0].id,'other-device');
  offline=true;assert.equal(stale.write([]),true);await settle();offline=false;
  assert.equal(stale.state.items[0].id,'other-device');assert.equal(server.items.length,1);
  stale.state.editing=true;server.items=[snapshot('deferred')];server.revision++;
  await stale.refresh();assert.equal(stale.state.items[0].id,'other-device');
  stale.state.editing=false;await stale.refresh();assert.equal(stale.state.items[0].id,'deferred');
  // A GET already in flight cannot clear the pending write lock or replace UI.
  let finishGet,finishPost;waitGet=new Promise(r=>finishGet=r);waitPost=new Promise(r=>finishPost=r);
  const refreshing=stale.refresh();assert.equal(stale.write([snapshot('racing')]),true);
  finishGet();await refreshing;assert.equal(stale.writable(),false);
  finishPost();await settle();waitGet=null;waitPost=null;assert.equal(server.items[0].id,'racing');
  assert.equal(stale.writable(),true);
  console.log('PASS: shared reads, cross-device edits, conflicts, offline rollback, editor isolation, request races and legacy data preservation');
})().catch(error=>{console.error(error);process.exitCode=1;});
