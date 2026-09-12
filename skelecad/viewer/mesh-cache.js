/* One parser worker, bounded content-addressed LRU, foreground before prefetch. */
"use strict";
(()=>{
  const entries=new Map(),queue=[];let worker=null,running=null,nextId=0,bytes=0,idleTimer=null,interactiveUntil=0;
  const limit=128*1024*1024;
  function remote(){return !['localhost','127.0.0.1','[::1]'].includes(new URL(window.location.href).hostname);}
  function scope(item){return new URL(item.path,window.location.href).pathname.replace(/\/files\/[^/]*$/,'');}
  function key(item){return (remote()&&!item.exact?'preview:'+scope(item)+':':'full:')+(item.part?.sha256||(item.path+':uncached:'+ (++nextId)));}
  function trim(){
    for(const [k,e] of entries){if(bytes<=limit)break;if(!e.value)continue;entries.delete(k);bytes-=e.bytes;}
  }
  function prioritize(entry){
    if(entry.prefetch||entry.value||!running?.prefetch||running===entry)return;
    queue.push(running);running=null;worker.terminate();worker=null;
  }
  function pump(){
    if(running||!queue.length)return;
    queue.sort((a,b)=>Number(a.prefetch)-Number(b.prefetch));
    if(queue[0].prefetch&&Date.now()<interactiveUntil){clearTimeout(idleTimer);idleTimer=setTimeout(pump,250);return;}
    if(!worker){
      worker=new Worker('mesh-worker.js?v=5');
      const parser=worker;
      worker.onmessage=({data})=>{
        if(worker!==parser)return;
        const entry=running;if(!entry||entry.id!==data.id)return;running=null;
        if(data.error){entries.delete(entry.key);entry.reject(new Error(data.error));}
        else{entry.value={mesh:data.mesh,sha256:data.sha256,detail:data.detail||'full'};entry.bytes=data.mesh.positions.byteLength+data.mesh.normals.byteLength;bytes+=entry.bytes;entry.resolve(entry.value);trim();}
        pump();
      };
      worker.onerror=()=>{if(worker!==parser)return;const entry=running;running=null;worker.terminate();worker=null;if(entry){entries.delete(entry.key);entry.reject(new Error('形状の読み込み処理が停止しました。'));}pump();};
    }
    running=queue.shift();worker.postMessage({id:running.id,url:running.url,sha256:running.sha256,compact:remote(),preview:remote()&&!running.exact});
  }
  function get(item,prefetch=false){
    const k=key(item);let entry=entries.get(k);
    if(entry){entries.delete(k);entries.set(k,entry);if(!prefetch)entry.prefetch=false;prioritize(entry);pump();return entry.promise;}
    entry={key:k,id:++nextId,url:new URL(item.path,window.location.href).href,sha256:item.part?.sha256,exact:Boolean(item.exact),prefetch,bytes:0};
    entry.promise=new Promise((resolve,reject)=>{entry.resolve=resolve;entry.reject=reject;});entries.set(k,entry);queue.push(entry);prioritize(entry);pump();return entry.promise;
  }
  function cancelPrefetch(){
    for(let i=queue.length-1;i>=0;i--)if(queue[i].prefetch){const [e]=queue.splice(i,1);entries.delete(e.key);e.reject(new Error('先読み対象が更新されました。'));}
    if(running?.prefetch){const e=running;running=null;worker.terminate();worker=null;entries.delete(e.key);e.reject(new Error('先読み対象が更新されました。'));pump();}
  }
  function canPrefetch(){
    const host=new URL(window.location.href).hostname;
    const connection=window.navigator?.connection;
    return ['localhost','127.0.0.1','[::1]'].includes(host)&&!connection?.saveData&&(!connection?.downlink||connection.downlink>2);
  }
  function retainSources(items){
    const wanted=new Set(items.map(item=>item.part?.sha256||new URL(item.path,window.location.href).href));
    const keep=e=>wanted.has(e.sha256||e.url);
    for(let i=queue.length-1;i>=0;i--)if(!keep(queue[i])){const [e]=queue.splice(i,1);entries.delete(e.key);e.reject(new Error('表示するモデルが変更されました。'));}
    if(running&&!keep(running)){const e=running;running=null;worker.terminate();worker=null;entries.delete(e.key);e.reject(new Error('表示するモデルが変更されました。'));}
    pump();
  }
  for(const type of ['pointerdown','pointermove','wheel','keydown'])window.addEventListener(type,()=>{interactiveUntil=Date.now()+500;},{passive:true});
  window.SkeleMeshCache={
    load:async item=>({...await get(item),part:item.part}),
    loadExact:async item=>({...await get({...item,exact:true}),part:item.part}),
    prefetch(items){cancelPrefetch();if(canPrefetch())for(const item of items)get(item,true).catch(()=>{});},
    canPrefetch,
    retainSources,
    cancelPrefetch,
    stats:()=>({bytes,limit,entries:entries.size,queued:queue.length,running:Boolean(running)})
  };
})();
