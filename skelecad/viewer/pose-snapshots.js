'use strict';
function createPoseSnapshots(api){
  const panel=document.getElementById('poseSnapshots'),list=document.getElementById('snapshotList'),flash=document.getElementById('snapshotFlash');
  const storageKey='skelecad.poseSnapshots.v1',maximum=30;let allItems=typeof createSharedSnapshotStore==='function'?[]:read(),defaultModel=String(api.model()||''),items=allItems.filter(item=>item.model===defaultModel),activeId=null,flashTimer=null;
  const deleteDistance=80,touchPointers=new Set();let cardDrag=null,suppressClickUntil=0;
  const shared=typeof createSharedSnapshotStore==='function'?createSharedSnapshotStore({
    isEditing:()=>Boolean(cardDrag),
    onChange(value){allItems=value;items=allItems.filter(item=>item.model===defaultModel).sort((a,b)=>(a.order??0)-(b.order??0));if(!items.some(item=>item.id===activeId))activeId=null;render();}
  }):null;
  function cancelDrag(){
    if(!cardDrag)return;
    cardDrag.card.classList?.remove('dragging');cardDrag.ghost?.remove();cardDrag.hint?.remove();
    list.querySelectorAll?.('.dragTarget').forEach(card=>card.classList.remove('dragTarget'));
    cardDrag=null;
  }
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
      const next=[...allItems.filter(item=>item.model!==defaultModel),...items];
      if(shared){if(!shared.write(next))return false;allItems=next;return true;}
      allItems=next;
      localStorage.setItem(storageKey,JSON.stringify(allItems));return true;
    }catch(_){return false;}
  }
  function escapeText(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function card(item,number){
    const selected=activeId===item.id?' aria-current="true"':'',label=`スナップショット${number}`;
    return `<article class="snapshotCard" data-id="${escapeText(item.id)}"${selected} draggable="false"><button class="snapshotRestore" type="button" aria-label="${label}を復元">${item.image?`<img src="${escapeText(item.image)}" alt="${label}のプレビュー" draggable="false">`:'<span class="snapshotPlaceholder" aria-hidden="true"></span>'}</button></article>`;
  }
  function addCard(){return `<article class="snapshotCard snapshotAddCard" data-id="add"><button class="snapshotAdd" type="button" aria-label="スナップショットを撮影"${items.length>=maximum?' disabled':''}><svg class="snapshotCameraIcon" aria-hidden="true" viewBox="0 0 32 32"><path d="M10 8.5 12.2 5h7.6L22 8.5h4.5A2.5 2.5 0 0 1 29 11v13.5a2.5 2.5 0 0 1-2.5 2.5h-21A2.5 2.5 0 0 1 3 24.5V11a2.5 2.5 0 0 1 2.5-2.5H10Zm6 3.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm0 2.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z"/></svg></button></article>`;}
  function render(){
    cancelDrag();
    const motion=api.motion(),active=Boolean(motion?.isActive());panel.hidden=!active;
    if(!active)return;
    list.innerHTML=addCard()+items.map((item,index)=>card(item,index+1)).join('');
  }
  function sync(){
    const active=Boolean(api.motion()?.isActive());panel.hidden=!active;if(!active){cancelDrag();return;}
    const model=String(api.model()||'');
    const unscoped=api.unscopedModel?.();
    if(!shared&&unscoped&&unscoped!==model&&allItems.some(item=>item.model===unscoped)){
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
    if(Date.now()<suppressClickUntil){event.preventDefault?.();return;}
    if(cardElement.dataset.id==='add'){save();return;}
    const item=items.find(entry=>entry.id===cardElement.dataset.id);if(item)restore(item);
  });
  function dropPosition(event){
    const bounds=panel.getBoundingClientRect(),x=event.clientX,y=event.clientY;
    const dx=Math.max(bounds.left-x,0,x-bounds.right),dy=Math.max(bounds.top-y,0,y-bounds.bottom);
    const inside=dx===0&&dy===0,remove=Math.hypot(dx,dy)>=deleteDistance;
    const horizontal=bounds.width>bounds.height;
    const cards=Array.from(list.querySelectorAll('.snapshotCard')).filter(card=>card.dataset.id!==cardDrag.id);
    let target=null,after=false;
    if(inside&&cards.length){
      target=cards.reduce((best,card)=>{const r=card.getBoundingClientRect(),d=Math.hypot(x-r.left-r.width/2,y-r.top-r.height/2);return !best||d<best.d?{card,d}:best;},null).card;
      const r=target.getBoundingClientRect();after=horizontal?x>r.left+r.width/2:y>r.top+r.height/2;
    }
    return {inside,remove,target,after,bounds,horizontal};
  }
  list.addEventListener('pointerdown',event=>{
    const card=event.target.closest?.('.snapshotCard'),id=card?.dataset.id;
    if(!id||id==='add'||event.button!==0||touchPointers.size>1||!api.motion()?.isActive())return;
    cancelDrag();cardDrag={id,card,model:defaultModel,pointerId:event.pointerId,x:event.clientX,y:event.clientY,moved:false};
  });
  document.addEventListener('pointerdown',event=>{
    if(event.pointerType==='touch')touchPointers.add(event.pointerId);
    if(cardDrag&&(cardDrag.pointerId!==event.pointerId||touchPointers.size>1)){suppressClickUntil=Date.now()+500;cancelDrag();}
  },true);
  document.addEventListener('pointermove',event=>{
    const drag=cardDrag;if(!drag||drag.pointerId!==event.pointerId)return;
    if(drag.model!==String(api.model()||'')||panel.hidden){cancelDrag();return;}
    if(!drag.moved){
      if(Math.hypot(event.clientX-drag.x,event.clientY-drag.y)<10)return;
      drag.moved=true;list.setPointerCapture(event.pointerId);drag.card.classList.add('dragging');
      const bounds=drag.card.getBoundingClientRect();drag.bounds=bounds;
      drag.ghost=drag.card.cloneNode(true);drag.ghost.className='snapshotCard snapshotDragGhost';drag.ghost.setAttribute('aria-hidden','true');drag.ghost.inert=true;
      Object.assign(drag.ghost.style,{left:bounds.left+'px',top:bounds.top+'px',width:bounds.width+'px',height:bounds.height+'px'});
      drag.hint=document.createElement('div');drag.hint.className='snapshotDragHint';drag.hint.setAttribute('role','status');
      document.body.append(drag.ghost,drag.hint);
    }
    event.preventDefault();
    const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
    drag.ghost.style.transform=`translate(${dx}px,${dy}px)`;
    const position=dropPosition(event);drag.ghost.dataset.delete=String(position.remove);
    drag.hint.textContent=position.remove?'離すと削除':position.inside?'並べ替え':'離すと元に戻ります';
    Object.assign(drag.hint.style,{left:Math.max(85,Math.min(window.innerWidth-85,event.clientX))+'px',top:Math.max(8,event.clientY-55)+'px'});
    list.querySelectorAll('.dragTarget').forEach(card=>card.classList.remove('dragTarget'));position.target?.classList.add('dragTarget');
    if(position.inside){const r=position.bounds;if(position.horizontal){if(event.clientX>r.right-24)panel.scrollLeft+=12;else if(event.clientX<r.left+24)panel.scrollLeft-=12;}else{if(event.clientY>r.bottom-24)panel.scrollTop+=12;else if(event.clientY<r.top+24)panel.scrollTop-=12;}}
  },{capture:true,passive:false});
  document.addEventListener('pointerup',event=>{
    touchPointers.delete(event.pointerId);const drag=cardDrag;if(!drag||drag.pointerId!==event.pointerId)return;
    if(!drag.moved){cancelDrag();return;}
    suppressClickUntil=Date.now()+500;
    const valid=drag.model===String(api.model()||'')&&!panel.hidden&&api.motion()?.isActive(),position=valid?dropPosition(event):null;
    cancelDrag();
    if(!valid||(!position.inside&&!position.remove))return;
    const previous=items.slice(),previousAll=allItems;
    if(position.remove)items=items.filter(item=>item.id!==drag.id);
    else if(position.target){
      const index=items.findIndex(item=>item.id===drag.id);if(index<0)return;
      const [item]=items.splice(index,1),targetId=position.target.dataset.id;
      const to=targetId==='add'?0:items.findIndex(entry=>entry.id===targetId)+(position.after?1:0);items.splice(Math.max(0,to),0,item);
    }
    if(!write()){items=previous;allItems=previousAll;}else if(position.remove&&activeId===drag.id)activeId=null;
    render();
  },true);
  for(const type of ['pointercancel','lostpointercapture'])document.addEventListener(type,event=>{if(type==='lostpointercapture'&&event.target!==list)return;touchPointers.delete(event.pointerId);if(cardDrag?.pointerId===event.pointerId){suppressClickUntil=Date.now()+500;cancelDrag();}},true);
  document.addEventListener('visibilitychange',()=>{cancelDrag();touchPointers.clear();});
  window.addEventListener('blur',()=>{cancelDrag();touchPointers.clear();});
  // Saved cards use pointer dragging on both phones and PCs, never native file dragging.
  panel.addEventListener('dragstart',event=>event.preventDefault());
  panel.addEventListener('contextmenu',event=>{if(event.target.closest?.('.snapshotCard'))event.preventDefault();});
  render();
  return {sync,render,items:()=>items.slice(),restore,clearSelection};
}
if(typeof module!=='undefined')module.exports={createPoseSnapshots};

'use strict';
function createMobilePoseSnapshots(api){
  const panel=document.getElementById('poseSnapshots'),list=document.getElementById('snapshotList'),flash=document.getElementById('snapshotFlash');
  const storageKey='skelecad.poseSnapshots.v1',maximum=30;let allItems=typeof createSharedSnapshotStore==='function'?[]:read(),defaultModel=String(api.model()||''),items=allItems.filter(item=>item.model===defaultModel),activeId=null,flashTimer=null;
  const editor=document.getElementById('snapshotEditor'),grid=document.getElementById('snapshotEditorGrid'),scroller=document.getElementById('snapshotEditorScroll'),editorStatus=document.getElementById('snapshotEditorStatus');
  const pendingDeletes=new Set(),touchPointers=new Set();let cardDrag=null,suppressClickUntil=0,draft=null,editModel=null,holdTimer=null,scrollFrame=null,focusBefore=null;
  const shared=typeof createSharedSnapshotStore==='function'?createSharedSnapshotStore({
    isEditing:()=>Boolean(cardDrag||draft),
    onChange(value){allItems=value;items=allItems.filter(item=>item.model===defaultModel).sort((a,b)=>(a.order??0)-(b.order??0));if(!items.some(item=>item.id===activeId))activeId=null;render();}
  }):null;
  function cancelDrag(){
    clearTimeout(holdTimer);holdTimer=null;
    if(scrollFrame!==null){cancelAnimationFrame(scrollFrame);scrollFrame=null;}
    const drag=cardDrag;cardDrag=null;
    if(!drag)return;
    drag.card.classList?.remove('dragging');drag.ghost?.remove();
    grid.querySelectorAll?.('.dragTarget').forEach(card=>card.classList.remove('dragTarget'));
    if(grid.hasPointerCapture?.(drag.pointerId))grid.releasePointerCapture(drag.pointerId);
  }
  function editorRender(){
    grid.innerHTML=draft.map((item,index)=>`<article class="snapshotEditCard${pendingDeletes.has(item.id)?' pendingDelete':''}" data-id="${escapeText(item.id)}">
      <button class="snapshotEditImage" type="button" aria-label="スナップショット${index+1}を長押しして移動">${item.image?`<img src="${escapeText(item.image)}" alt="スナップショット${index+1}" draggable="false">`:'<span class="snapshotPlaceholder"></span>'}</button>
      <button class="snapshotEditDelete" type="button" aria-label="スナップショット${index+1}${pendingDeletes.has(item.id)?'の削除を取り消す':'を削除'}" aria-pressed="${pendingDeletes.has(item.id)}">${pendingDeletes.has(item.id)?'↶':'×'}</button>
      
    </article>`).join('');
    editorStatus.textContent=draft.length?'長押しで移動 · スワイプでスクロール':'スナップショットはありません。✓で削除を確定します。';
  }
  function openEditor(){
    if(draft||!api.motion()?.isActive()||!items.length)return;
    if(shared&&!shared.writable())return;
    cancelDrag();pendingDeletes.clear();editModel=defaultModel;draft=items.map(item=>({...item}));focusBefore=document.activeElement;
    editorRender();editor.showModal();scroller.scrollTop=0;
    document.getElementById('snapshotEditorCancel').focus?.();
    suppressClickUntil=Date.now()+500;
  }
  function closeEditor(commit=false){
    if(!draft)return;
    cancelDrag();
    if(commit){
      if(editModel!==String(api.model()||'')||!api.motion()?.isActive()){closeEditor(false);return;}
      const previous=items,previousAll=allItems;items=draft.filter(item=>!pendingDeletes.has(item.id));
      if(!write()){items=previous;allItems=previousAll;editorStatus.textContent='保存できませんでした。空き容量を確認して再度お試しください。';return;}
      if(!items.some(item=>item.id===activeId))activeId=null;
    }
    draft=null;editModel=null;editor.close();render();focusBefore?.focus?.();
  }
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
      const next=[...allItems.filter(item=>item.model!==defaultModel),...items];
      if(shared){if(!shared.write(next))return false;allItems=next;return true;}
      allItems=next;
      localStorage.setItem(storageKey,JSON.stringify(allItems));return true;
    }catch(_){return false;}
  }
  function escapeText(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function card(item,number){
    const selected=activeId===item.id?' aria-current="true"':'',label=`スナップショット${number}`;
    return `<article class="snapshotCard" data-id="${escapeText(item.id)}"${selected} draggable="false"><button class="snapshotRestore" type="button" aria-label="${label}を復元">${item.image?`<img src="${escapeText(item.image)}" alt="${label}のプレビュー" draggable="false">`:'<span class="snapshotPlaceholder" aria-hidden="true"></span>'}</button></article>`;
  }
  function addCard(){return `<article class="snapshotCard snapshotAddCard" data-id="add"><button class="snapshotAdd" type="button" aria-label="スナップショットを撮影"${items.length>=maximum?' disabled':''}><svg class="snapshotCameraIcon" aria-hidden="true" viewBox="0 0 32 32"><path d="M10 8.5 12.2 5h7.6L22 8.5h4.5A2.5 2.5 0 0 1 29 11v13.5a2.5 2.5 0 0 1-2.5 2.5h-21A2.5 2.5 0 0 1 3 24.5V11a2.5 2.5 0 0 1 2.5-2.5H10Zm6 3.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm0 2.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z"/></svg></button></article>`;}
  function render(){
    cancelDrag();
    const motion=api.motion(),active=Boolean(motion?.isActive());panel.hidden=!active;
    if(!active)return;
    list.innerHTML=addCard()+items.map((item,index)=>card(item,index+1)).join('');
  }
  function sync(){
    const active=Boolean(api.motion()?.isActive());panel.hidden=!active;if(!active){cancelDrag();closeEditor(false);return;}
    const model=String(api.model()||'');
    const unscoped=api.unscopedModel?.();
    if(!shared&&unscoped&&unscoped!==model&&allItems.some(item=>item.model===unscoped)){
      allItems=allItems.map(item=>item.model===unscoped?{...item,model}:item);
      try{localStorage.setItem(storageKey,JSON.stringify(allItems));}catch(_){}
      defaultModel='';
    }
    if(model!==defaultModel){closeEditor(false);defaultModel=model;items=allItems.filter(item=>item.model===model).sort((a,b)=>(a.order??0)-(b.order??0));activeId=null;render();}
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
    if(Date.now()<suppressClickUntil){event.preventDefault?.();return;}
    if(cardElement.dataset.id==='add'){save();return;}
    const item=items.find(entry=>entry.id===cardElement.dataset.id);if(item)restore(item);
  });
  function targetAt(x,y){
    const bounds=scroller.getBoundingClientRect();
    if(x<bounds.left||x>bounds.right||y<bounds.top||y>bounds.bottom)return null;
    const cards=Array.from(grid.querySelectorAll('.snapshotEditCard')).filter(card=>card.dataset.id!==cardDrag.id);
    const target=cards.reduce((best,card)=>{const r=card.getBoundingClientRect(),d=Math.hypot(x-r.left-r.width/2,y-r.top-r.height/2);return !best||d<best.d?{card,d}:best;},null)?.card;
    if(!target)return null;
    const r=target.getBoundingClientRect();return {id:target.dataset.id,after:y>r.bottom||(y>=r.top&&x>r.left+r.width/2),card:target};
  }
  function markTarget(){
    grid.querySelectorAll('.dragTarget').forEach(card=>card.classList.remove('dragTarget'));
    const target=targetAt(cardDrag.lastX,cardDrag.lastY);target?.card.classList.add('dragTarget');
  }
  function autoScroll(){
    if(!cardDrag?.lifted)return;
    const r=scroller.getBoundingClientRect(),y=cardDrag.lastY;
    const amount=y<r.top+48?-Math.min(12,(r.top+48-y)/4):y>r.bottom-48?Math.min(12,(y-r.bottom+48)/4):0;
    if(amount){scroller.scrollTop+=amount;markTarget();}
    scrollFrame=requestAnimationFrame(autoScroll);
  }
  function begin(event,inEditor){
    const selector=inEditor?'.snapshotEditCard':'.snapshotCard',card=event.target.closest?.(selector),id=card?.dataset.id;
    if(!id||id==='add'||event.button!==0||touchPointers.size>1||!api.motion()?.isActive()||event.target.closest?.('.snapshotEditDelete'))return;
    cancelDrag();
    const drag=cardDrag={id,card,inEditor,pointerId:event.pointerId,x:event.clientX,y:event.clientY,lastX:event.clientX,lastY:event.clientY,lifted:false,scrolling:false};
    holdTimer=setTimeout(()=>{
      if(cardDrag!==drag)return;
      if(!inEditor){openEditor();return;}
      drag.lifted=true;suppressClickUntil=Date.now()+500;
      grid.setPointerCapture?.(drag.pointerId);card.classList.add('dragging');
      const r=card.getBoundingClientRect();drag.ghost=card.cloneNode(true);drag.ghost.className='snapshotEditGhost';drag.ghost.inert=true;drag.ghost.setAttribute('aria-hidden','true');
      Object.assign(drag.ghost.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});
      editor.append(drag.ghost);editorStatus.textContent='移動先で指を離してください';autoScroll();
    },450);
  }
  list.addEventListener('pointerdown',event=>begin(event,false));
  grid.addEventListener('pointerdown',event=>begin(event,true));
  document.addEventListener('pointerdown',event=>{
    if(event.pointerType==='touch')touchPointers.add(event.pointerId);
    if(cardDrag&&(cardDrag.pointerId!==event.pointerId||touchPointers.size>1)){suppressClickUntil=Date.now()+500;cancelDrag();}
  },true);
  document.addEventListener('pointermove',event=>{
    const drag=cardDrag;if(!drag||drag.pointerId!==event.pointerId)return;
    if(!drag.lifted&&Math.hypot(event.clientX-drag.x,event.clientY-drag.y)>10){
      clearTimeout(holdTimer);holdTimer=null;suppressClickUntil=Date.now()+500;
      if(!drag.inEditor){cancelDrag();return;}
      drag.scrolling=true;
    }
    if(drag.inEditor){
      event.preventDefault();
      if(drag.lifted){drag.ghost.style.transform=`translate(${event.clientX-drag.x}px,${event.clientY-drag.y}px)`;}
      else if(drag.scrolling)scroller.scrollTop+=drag.lastY-event.clientY;
    }
    drag.lastX=event.clientX;drag.lastY=event.clientY;
    if(drag.lifted)markTarget();
  },{capture:true,passive:false});
  document.addEventListener('pointerup',event=>{
    touchPointers.delete(event.pointerId);const drag=cardDrag;if(!drag||drag.pointerId!==event.pointerId)return;
    const target=drag.lifted?targetAt(event.clientX,event.clientY):null;
    if(drag.lifted||drag.scrolling)suppressClickUntil=Date.now()+500;
    cancelDrag();
    if(target&&draft){
      const index=draft.findIndex(item=>item.id===drag.id);if(index<0)return;
      const [item]=draft.splice(index,1),to=draft.findIndex(item=>item.id===target.id)+(target.after?1:0);
      draft.splice(Math.max(0,to),0,item);editorRender();
    }else if(draft)editorStatus.textContent='長押しで移動 · スワイプでスクロール';
  },true);
  for(const type of ['pointercancel','lostpointercapture'])document.addEventListener(type,event=>{
    if(type==='lostpointercapture'&&event.target!==grid)return;
    touchPointers.delete(event.pointerId);
    if(cardDrag?.pointerId===event.pointerId){suppressClickUntil=Date.now()+500;cancelDrag();}
  },true);
  grid.addEventListener('click',event=>{
    if(Date.now()<suppressClickUntil||!draft)return;
    const card=event.target.closest?.('.snapshotEditCard');if(!card)return;
    const index=draft.findIndex(item=>item.id===card.dataset.id);if(index<0)return;
    if(!event.target.closest?.('.snapshotEditDelete'))return;
    const id=draft[index].id;
    if(pendingDeletes.has(id))pendingDeletes.delete(id);else pendingDeletes.add(id);
    editorRender();
  });
  list.addEventListener('keydown',event=>{if(event.key==='F2'){event.preventDefault();openEditor();}});
  document.getElementById('snapshotEditorDone').addEventListener('click',()=>closeEditor(true));
  document.getElementById('snapshotEditorCancel').addEventListener('click',()=>closeEditor(false));
  editor.addEventListener('cancel',event=>{event.preventDefault();closeEditor(false);});
  editor.addEventListener('close',()=>{if(draft){draft=null;editModel=null;cancelDrag();}});
  document.addEventListener('visibilitychange',()=>{cancelDrag();touchPointers.clear();});
  window.addEventListener('blur',()=>{cancelDrag();touchPointers.clear();});
  for(const surface of [panel,editor]){
    surface.addEventListener('dragstart',event=>event.preventDefault());
    surface.addEventListener('contextmenu',event=>event.preventDefault());
  }
  render();
  return {sync,render,items:()=>items.slice(),restore,clearSelection};
}
if(typeof module!=='undefined')module.exports={createPoseSnapshots,createMobilePoseSnapshots};
