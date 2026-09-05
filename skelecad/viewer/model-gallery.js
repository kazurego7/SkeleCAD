'use strict';
function createModelGallery(){
  const select=document.getElementById('modelSelect'),openButton=document.getElementById('modelPicker'),dialog=document.getElementById('modelGallery'),list=document.getElementById('modelGalleryList'),closeButton=document.getElementById('modelGalleryClose');
  const title=document.getElementById('modelGalleryTitle'),trashOpen=document.getElementById('modelTrashOpen'),trashBack=document.getElementById('modelTrashBack'),trashEmpty=document.getElementById('modelTrashEmpty'),status=document.getElementById('modelGalleryStatus');
  if(!select||!openButton||!dialog||!list)return {refresh(){}};
  const storageKey='skelecad.modelThumbnails.v1',maximum=60;
  let thumbnails=readThumbnails(),trashMode=false,trashed=[];
  function readThumbnails(){
    try{const value=JSON.parse(localStorage.getItem(storageKey)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch(_){return {};}
  }
  function persistThumbnails(){try{localStorage.setItem(storageKey,JSON.stringify(thumbnails));}catch(_){}}
  function saveThumbnail(){
    if(document.getElementById('gl')?.dataset.loaded!=='true')return;
    const image=window.SkeleViewer?.capturePreview?.();if(!image)return;
    thumbnails[select.value]=image;
    const entries=Object.entries(thumbnails);if(entries.length>maximum)thumbnails=Object.fromEntries(entries.slice(-maximum));
    persistThumbnails();
  }
  async function request(path,options){
    const response=await fetch('../api/'+path,{cache:'no-store',...(options||{})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||'操作に失敗しました。');
    return data;
  }
  async function mutate(path){
    const session=await request('session');
    return request(path,{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':session.token},body:'{}'});
  }
  function showError(message=''){if(!status)return;status.textContent=message;status.hidden=!message;}
  function placeholder(){const value=document.createElement('span');value.className='modelCardPlaceholder';value.textContent='◇';value.setAttribute('aria-hidden','true');return value;}
  function imageFor(url){
    if(!url)return placeholder();
    const image=document.createElement('img');image.className='modelCardImage';image.src=url;image.alt='';image.addEventListener('error',()=>image.replaceWith(placeholder()));return image;
  }
  function cardText(nameValue){
    const text=document.createElement('span');text.className='modelCardText';const name=document.createElement('span');name.className='modelCardName';name.textContent=nameValue;
    text.append(name);return text;
  }
  function setMode(isTrash){
    trashMode=isTrash;title.textContent=isTrash?'ゴミ箱':'3Dモデル';trashOpen.hidden=isTrash;trashBack.hidden=!isTrash;trashEmpty.hidden=!isTrash||!trashed.length;showError();
  }
  function renderMain(){
    const selected=Array.from(select.options).find(option=>option.value===select.value);
    openButton.textContent=selected?.textContent||'3Dモデルを選ぶ';openButton.title='表示する3Dモデルを選ぶ';list.replaceChildren();
    for(const option of Array.from(select.options)){
      const card=document.createElement('article');card.className='modelCard';card.setAttribute('aria-current',String(option.value===select.value));
      const choose=document.createElement('button');choose.type='button';choose.className='modelCardSelect';choose.dataset.value=option.value;
      choose.append(imageFor(thumbnails[option.value]||option.dataset.thumbnail),cardText(option.textContent));card.append(choose);
      if(option.value.startsWith('job:')){const remove=document.createElement('button');remove.type='button';remove.className='modelCardTrash';remove.dataset.id=option.value.slice(4);remove.setAttribute('aria-label',option.textContent+'をゴミ箱へ移動');remove.title='ゴミ箱へ移動';remove.textContent='×';card.append(remove);}
      list.append(card);
    }
  }
  function renderTrash(){
    list.replaceChildren();trashEmpty.hidden=!trashed.length;
    if(!trashed.length){const empty=document.createElement('p');empty.className='modelGalleryEmpty';empty.textContent='ゴミ箱は空です';list.append(empty);return;}
    for(const job of trashed){
      const card=document.createElement('article');card.className='modelCard';
      const content=document.createElement('div');content.className='modelCardSelect';const footer=cardText(job.name||'3Dモデル');footer.className+=' modelCardTextWithAction';
      const restore=document.createElement('button');restore.type='button';restore.className='modelCardRestore';restore.dataset.id=job.id;restore.textContent='復元';restore.setAttribute('aria-label',(job.name||'3Dモデル')+'を復元');footer.append(restore);
      content.append(imageFor(thumbnails['job:'+job.id]||'../api/trash/'+job.id+'/files/source.png'),footer);card.append(content);list.append(card);
    }
  }
  function refresh(){if(trashMode)renderTrash();else renderMain();}
  function removeOption(value){
    const option=Array.from(select.options).find(item=>item.value===value);if(!option)return false;
    option.remove?.();if(Array.from(select.options).includes(option)){const index=Array.from(select.options).indexOf(option);if(index>=0)select.options.splice(index,1);}return true;
  }
  openButton.addEventListener('click',()=>{saveThumbnail();setMode(false);refresh();dialog.showModal();});
  trashOpen?.addEventListener('click',async()=>{trashOpen.disabled=true;showError();try{const data=await request('trash');trashed=data.jobs||[];setMode(true);renderTrash();}catch(error){showError(error.message);}finally{trashOpen.disabled=false;}});
  trashBack?.addEventListener('click',()=>{setMode(false);renderMain();});
  trashEmpty?.addEventListener('click',async()=>{trashEmpty.disabled=true;showError();try{const result=await mutate('trash/empty');for(const id of result.deleted||[])delete thumbnails['job:'+id];persistThumbnails();trashed=[];renderTrash();}catch(error){showError(error.message);}finally{trashEmpty.disabled=false;}});
  closeButton?.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  list.addEventListener('click',async event=>{
    const remove=event.target.closest?.('.modelCardTrash');
    if(remove){remove.disabled=true;showError();try{const value='job:'+remove.dataset.id,wasSelected=select.value===value;await mutate('jobs/'+remove.dataset.id+'/trash');removeOption(value);
        if(wasSelected){select.value=Array.from(select.options)[0]?.value||'';select.dispatchEvent(new Event('change',{bubbles:true}));}renderMain();}
      catch(error){showError(error.message);remove.disabled=false;}return;}
    const restore=event.target.closest?.('.modelCardRestore');
    if(restore){restore.disabled=true;showError();try{const job=await mutate('trash/'+restore.dataset.id+'/restore');trashed=trashed.filter(item=>item.id!==job.id);window.SkeleCADWorkflow?.restoreJob?.(job);renderTrash();}
      catch(error){showError(error.message);restore.disabled=false;}return;}
    const choose=event.target.closest?.('.modelCardSelect');if(!choose?.dataset.value)return;select.value=choose.dataset.value;select.dispatchEvent(new Event('change',{bubbles:true}));dialog.close();renderMain();
  });
  select.addEventListener('change',refresh);setMode(false);refresh();
  return {refresh,items:()=>Array.from(select.options).map(option=>option.value)};
}
if(typeof window!=='undefined')window.SkeleModelGallery=createModelGallery();
if(typeof module!=='undefined')module.exports={createModelGallery};
