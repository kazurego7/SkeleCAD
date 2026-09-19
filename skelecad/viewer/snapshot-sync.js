'use strict';
// One shared collection for both layouts; revision checks prevent stale writes.
function createSnapshotSync(options){
  const pendingKey='skelecad.poseSnapshots.unsent';
  const copy=value=>JSON.parse(JSON.stringify(value));
  const storage=options.storage,request=options.request;
  let revision=null,busy=false,reading=false,confirmed=[],token=null;
  function accept(value){
    if(value.unchanged)return;
    revision=value.revision;confirmed=copy(value.items);
    options.onChange(copy(confirmed));
  }
  async function post(items){
    if(!token)token=(await request('session')).token;
    return request('snapshots',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},body:JSON.stringify({revision,items})});
  }
  async function refresh(){
    if(busy||reading||options.isEditing())return;
    reading=true;
    try{
      const value=await request('snapshots'+(revision===null?'':'?since='+revision));
      // A user may have started dragging or saving during the network request.
      if(busy||options.isEditing())return;
      accept(value);options.notify('');
    }catch(error){token=null;options.notify(error.message||'スナップショットを同期できません。接続を確認してください。',true);}
    finally{reading=false;}
  }
  function writable(){
    if(revision===null||busy){options.notify(busy?'スナップショットを保存中です。少し待ってください。':'一覧の読み込みが終わってから保存できます。',true);return false;}
    return true;
  }
  function write(items){
    if(!writable())return false;
    const payload=copy(items);
    try{storage.setItem(pendingKey,JSON.stringify(payload));}
    catch(_){options.notify('端末の空き容量が不足しているため保存できません。',true);return false;}
    busy=true;
    post(payload).then(value=>{
      accept(value);storage.removeItem(pendingKey);options.notify('');
    }).catch(error=>{
      token=null;options.onChange(copy(confirmed));
      options.notify((error.message||'保存できませんでした。接続を確認してください。')+' 今回の変更は未反映です。',true);
      // The unsent edit remains in a separate local backup, never auto-uploaded.
    }).finally(()=>{busy=false;});
    return true;
  }
  return {refresh,write,writable};
}

function createSharedSnapshotStore(options){
  let notice=null,noticeTimer=null;
  function notify(message,persistent=false){
    if(!notice){
      notice=document.createElement('div');notice.setAttribute('role','status');notice.id='snapshotSyncNotice';
      Object.assign(notice.style,{position:'fixed',zIndex:'10000',left:'50%',top:'calc(env(safe-area-inset-top, 0px) + 64px)',transform:'translateX(-50%)',maxWidth:'min(440px, 90vw)',width:'max-content',padding:'8px 12px',borderRadius:'8px',background:'#25343c',color:'#fff',fontSize:'12px',pointerEvents:'none',boxSizing:'border-box'});
      document.body.append(notice);
    }
    clearTimeout(noticeTimer);notice.textContent=message;notice.hidden=!message;
    if(message&&!persistent)noticeTimer=setTimeout(()=>notice.hidden=true,4500);
  }
  const base=new URL('../api/',location.href);
  const store=createSnapshotSync({...options,storage:localStorage,notify,
    async request(path,init){
      const response=await fetch(new URL(path,base),{cache:'no-store',...init,signal:AbortSignal.timeout(30000)});
      const data=await response.json();if(!response.ok)throw new Error(data.error||'スナップショットを同期できません。');return data;
    }
  });
  setTimeout(()=>store.refresh(),0);
  setInterval(()=>{if(!document.hidden)store.refresh();},4000);
  window.addEventListener('focus',()=>store.refresh());
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)store.refresh();});
  return store;
}
if(typeof module!=='undefined')module.exports={createSnapshotSync};
