'use strict';
function createPoseSnapshots(api){
  const panel=document.getElementById('poseSnapshots'),list=document.getElementById('snapshotList'),flash=document.getElementById('snapshotFlash');
  const storageKey='skelecad.poseSnapshots.v1',maximum=30;let allItems=read(),defaultModel=String(api.model()||''),items=allItems.filter(item=>item.model===defaultModel),activeId=null,flashTimer=null,dragId='';
  function read(){
    try{
      const value=JSON.parse(localStorage.getItem(storageKey)||'[]'),clean=Array.isArray(value)?value.filter(item=>item&&item.schema===1&&Array.isArray(item.joints)):[];
      clean.sort(clean.every(item=>Number.isFinite(item.order))?(a,b)=>a.order-b.order:(a,b)=>String(b.createdAt||'').localeCompare(String(a.createdAt||'')));
      return clean.map((item,index)=>({...item,order:index}));
    }catch(_){return [];}
  }
  function write(){
    try{
      items.forEach((item,index)=>item.order=index);
      allItems=[...allItems.filter(item=>item.model!==defaultModel),...items];
      localStorage.setItem(storageKey,JSON.stringify(allItems));return true;
    }catch(_){return false;}
  }
  function escapeText(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function card(item,number){
    const selected=activeId===item.id?' aria-current="true"':'',label=`スナップショット${number}`;
    return `<article class="snapshotCard" data-id="${escapeText(item.id)}"${selected} draggable="true"><button class="snapshotRestore" type="button" aria-label="${label}を復元">${item.image?`<img src="${item.image}" alt="${label}のプレビュー" draggable="false">`:'<span class="snapshotPlaceholder" aria-hidden="true"></span>'}</button><button class="snapshotDelete" type="button" aria-label="${label}を削除" title="削除">×</button></article>`;
  }
  function addCard(){return `<article class="snapshotCard snapshotAddCard" data-id="add"><button class="snapshotAdd" type="button" aria-label="スナップショットを撮影"${items.length>=maximum?' disabled':''}><svg class="snapshotCameraIcon" aria-hidden="true" viewBox="0 0 32 32"><path d="M10 8.5 12.2 5h7.6L22 8.5h4.5A2.5 2.5 0 0 1 29 11v13.5a2.5 2.5 0 0 1-2.5 2.5h-21A2.5 2.5 0 0 1 3 24.5V11a2.5 2.5 0 0 1 2.5-2.5H10Zm6 3.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm0 2.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z"/></svg></button></article>`;}
  function render(){
    const motion=api.motion(),active=Boolean(motion?.isActive());panel.hidden=!active;
    if(!active)return;
    list.innerHTML=addCard()+items.map((item,index)=>card(item,index+1)).join('');
  }
  function sync(){
    const active=Boolean(api.motion()?.isActive());panel.hidden=!active;if(!active)return;
    const model=String(api.model()||'');
    const unscoped=api.unscopedModel?.();
    if(unscoped&&unscoped!==model&&allItems.some(item=>item.model===unscoped)){
      allItems=allItems.map(item=>item.model===unscoped?{...item,model}:item);
      try{localStorage.setItem(storageKey,JSON.stringify(allItems));}catch(_){}
      defaultModel='';
    }
    if(model!==defaultModel){defaultModel=model;items=allItems.filter(item=>item.model===model).sort((a,b)=>(a.order??0)-(b.order??0));activeId=null;render();}
  }
  function currentSnapshot(){
    const motion=api.motion(),state=motion?.reviewState();if(!motion?.isActive()||!state)return null;
    const pose=state.pose||{},joints=motion.joints().map(j=>({...j,angles:(pose[j.name]||[0,0,0]).slice()}));
    return {schema:1,id:'pose_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,7),name:'スナップショット '+(items.length+1),createdAt:new Date().toISOString(),model:api.model(),camera:api.camera(),joints,image:api.capture()};
  }
  function triggerFlash(){
    if(!flash)return;
    clearTimeout(flashTimer);flash.hidden=false;flash.className='active';
    flashTimer=setTimeout(()=>{flash.hidden=true;flash.className='';flashTimer=null;},280);
  }
  function save(){
    if(items.length>=maximum)return;
    const snapshot=currentSnapshot();if(!snapshot)return;
    items.unshift(snapshot);if(!write()){items.shift();return;}activeId=snapshot.id;triggerFlash();render();
  }
  function restore(item){
    api.setCamera(item.camera||null);api.motion()?.restore(item);activeId=item.id;render();api.requestRender();
  }
  function clearSelection(){activeId=null;render();}
  list.addEventListener('click',event=>{
    const cardElement=event.target.closest?.('.snapshotCard');if(!cardElement)return;
    if(event.target.closest?.('.snapshotDelete')){items=items.filter(entry=>entry.id!==cardElement.dataset.id);write();if(activeId===cardElement.dataset.id)activeId=null;render();return;}
    if(cardElement.dataset.id==='add'){save();return;}
    const item=items.find(entry=>entry.id===cardElement.dataset.id);if(item)restore(item);
  });
  list.addEventListener('dragstart',event=>{
    const cardElement=event.target.closest?.('.snapshotCard'),id=cardElement?.dataset.id;
    if(!id||id==='add'){event.preventDefault();return;}
    dragId=id;cardElement.classList?.add('dragging');event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('application/x-skelecad-snapshot',id);
  });
  list.addEventListener('dragover',event=>{
    const cardElement=event.target.closest?.('.snapshotCard'),id=cardElement?.dataset.id;
    if(!dragId||id===dragId)return;
    event.preventDefault();event.dataTransfer.dropEffect='move';
    const bounds=panel.getBoundingClientRect?.();if(bounds){if(event.clientY>bounds.bottom-48)panel.scrollTop+=18;else if(event.clientY<bounds.top+48)panel.scrollTop-=18;}
    list.querySelectorAll?.('.dragTarget').forEach(entry=>entry.classList.remove('dragTarget'));if(id!=='add')cardElement?.classList?.add('dragTarget');
  });
  list.addEventListener('drop',event=>{
    const cardElement=event.target.closest?.('.snapshotCard'),targetId=cardElement?.dataset.id;
    event.preventDefault();
    const from=items.findIndex(entry=>entry.id===dragId),target=items.findIndex(entry=>entry.id===targetId);
    if(from>=0){
      const [moved]=items.splice(from,1);
      if(targetId==='add')items.unshift(moved);
      else if(target<0)items.push(moved);
      else{const rect=cardElement.getBoundingClientRect?.(),after=rect&&event.clientY>rect.top+rect.height/2;let to=target+(after?1:0);if(from<to)to--;items.splice(Math.max(0,Math.min(to,items.length)),0,moved);}
      write();
    }
    dragId='';render();
  });
  list.addEventListener('dragend',()=>{dragId='';render();});
  // Only saved-card reordering may begin a native drag. The add card never
  // expose a generated JPEG as a File to the full-window image import handler.
  panel.addEventListener('dragstart',event=>{const id=event.target.closest?.('.snapshotCard')?.dataset.id;if(!id||id==='add')event.preventDefault();});
  render();
  return {sync,render,items:()=>items.slice(),restore,clearSelection};
}
if(typeof module!=='undefined')module.exports={createPoseSnapshots};
