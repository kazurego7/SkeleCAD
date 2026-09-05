/* Image jobs have their own identities; changing the viewer never rewrites a print. */
"use strict";
(()=>{
  const input=document.getElementById('imageUpload'),upload=document.getElementById('uploadImage');
  const line=document.getElementById('workflowStatus'),drop=document.getElementById('imageDrop');
  const progressBox=document.getElementById('generationProgress'),progressBar=document.getElementById('generationProgressBar'),progressText=document.getElementById('generationProgressText');
  const pauseButton=document.getElementById('generationPause'),stopButton=document.getElementById('generationStop');
  const partitionButton=document.getElementById('partitionAdjust');
  const symmetrySide=document.getElementById('symmetrySide'),restoreSymmetry=document.getElementById('restoreSymmetry');
  const returnToPartition=document.getElementById('returnToPartition');
  const printState=document.getElementById('printState');
  const jobs=new Map();let token=null,uploading=false,depth=0,lastLoaded=null;
  const manifestCache=new Map();let prefetched=null;
  function readManifest(job,filename){
    const key=job.id+':'+job.manifest_sha256+':'+filename;
    if(!manifestCache.has(key)){
      const promise=request('jobs/'+job.id+'/files/'+filename).catch(error=>{manifestCache.delete(key);throw error;});
      manifestCache.set(key,promise);
      if(manifestCache.size>12)manifestCache.delete(manifestCache.keys().next().value);
    }
    return manifestCache.get(key);
  }
  async function prefetchStages(job){
    if(!window.SkeleMeshCache||!job?.manifest||window.SkelePartition?.hasPendingChanges())return;
    const key=job.id+':'+job.manifest_sha256+':'+(job.background?.manifest_sha256||'');if(prefetched===key)return;prefetched=key;
    try{
      const preview=await readManifest(job,'manifest.json');
      const items=[{part:{sha256:preview.geometry?.sha256},path:api+'jobs/'+job.id+'/files/appearance.stl'},...preview.parts.map(part=>({part,path:part.path}))];
      const revision=job.mechanical_revision||job.background?.revision;
      if(revision){const result=await readManifest(job,'r_'+revision+'.json');items.push(...result.parts.map(part=>({part,path:part.path})));}
      if(prefetched===key&&modelSelect.value==='job:'+job.id&&!window.SkelePartition?.hasPendingChanges())window.SkeleMeshCache.prefetch(items.filter(item=>item.part.sha256));
    }catch(error){if(prefetched===key)prefetched=null;}
  }
  let viewedStep=null,viewedJob=null,lastStage=null,pendingOpen=null,opening=false,preparing=false,navigation=0;
  const stepButtons=Array.from({length:5},(_,i)=>document.getElementById('step'+i));
  const hint=document.getElementById('workflowHint'),imagePanel=document.getElementById('workflowImage'),sourceImage=document.getElementById('workflowSource');
  async function retainedMotion(job,isCurrent){
        const prior=job.previous_motion;
        const previous=await readManifest({...job,manifest_sha256:prior.manifest_sha256},'r_'+prior.revision+'.json');
        if(!isCurrent())return null;
        const changed=new Set(prior.changed_marker_names);
        const local=window.SkelePartition?.pendingMarkers?.();
        if(local){
          const latest=new Map(local.map(m=>[m.name,m])),old=new Map(previous.joints.map(j=>[j.name,j]));
          for(const name of new Set([...latest.keys(),...old.keys()])){
            const a=latest.get(name),b=old.get(name);
            if(!a||!b||JSON.stringify(a.center)!==JSON.stringify(b.center)||a.radius_mm!==b.radius_mm){
              changed.add(name);
            }
          }
        }
        // This is the previous fully validated assembly, not a mixture of old and new geometry.
        // Nearby unchanged joints can still be inspected on that assembly.
        const joints=previous.joints.map(j=>({...j,motion_ready:!changed.has(j.name)}));
        return {...previous,preview_only:true,print_ready:false,joints};
  }
  function currentStep(job){
    if(!job)return 0;
    if(job.stage==='print_ready'||job.stage==='print_failed'||job.stage==='printing'||(job.operation==='print'&&active.has(job.stage)))return 3;
    if(job.mechanical_revision||job.stage==='machining'||job.stage==='machining_failed'||(job.operation==='machine'&&active.has(job.stage)))return 3;
    if(job.partition_revision||job.stage==='partitioning'||job.stage==='partition_failed')return 2;
    return 1;
  }
  function viewRevision(job){
    const base=job.manifest+':'+(job.manifest_sha256||'');
    return viewedStep===3?base+':'+(job.background?.stage||'')+':'+(job.background?.manifest_sha256||'')+':'+(job.background?.preview?.manifest_sha256||'')+':'+JSON.stringify(job.previous_motion||null)+':'+JSON.stringify(window.SkelePartition?.pendingMarkers?.()||null):base;
  }
  function stepControls(job){
    if(viewedJob!==job?.id){viewedJob=job?.id;viewedStep=null;lastStage=null;}
    lastStage=job?.stage;
    const step=viewedStep??currentStep(job),busy=job&&active.has(job.stage);
    const canVisitJoints=Boolean(job?.manifest)&&(job?.previous_motion||((job?.background?.stage!=='failed'||job?.background?.preview?.ready_joint_count>0)&&job?.stage!=='machining_failed'));
    const partitionFailed=job?.background?.stage==='failed'||['partition_failed','machining_failed'].includes(job?.stage);
    const pending=Boolean(window.SkelePartition?.hasPendingChanges());
    const failed=Boolean(job?.error)||partitionFailed||job?.stage?.endsWith('_failed')||job?.background?.stage==='print_failed';
    const preparingBackground=['working','mechanical_ready'].includes(job?.background?.stage);
    const canPrepare=Boolean(job?.mechanical_revision||job?.background?.stage==='ready')&&!busy&&!pending&&!failed&&!preparingBackground;
    const available=[true,Boolean(job?.manifest),Boolean(job?.manifest),canVisitJoints,canPrepare];
    const running=Boolean(busy&&job.stage!=='paused');
    const operation=job?.operation;
    const loading=[false,
      running&&(job.stage==='symmetrizing'||(!job.manifest&&!['machine','print','partition'].includes(operation))),
      running&&(job.stage==='partitioning'||operation==='partition'),
      (running&&['partition','machine'].includes(operation))||window.SkelePartition?.hasPendingChanges()||(job?.background?.stage==='working'&&!job.background.revision),
      (running&&(job.stage==='printing'||operation==='print'))||job?.background?.stage==='mechanical_ready'||opening||preparing];
    stepButtons.forEach((button,i)=>{
      if(!button)return;
      button.disabled=!available[i]||(i===4&&(opening||preparing));
      button.dataset.current=String(i===step);
      button.dataset.complete=String(i<currentStep(job)||(i===4&&job?.stage==='print_ready'));
      const stepFailed=(i===2&&partitionFailed)||(i===4&&(job?.background?.stage==='print_failed'||job?.stage==='print_failed'));
      const warning=i===3&&partitionFailed;
      button.dataset.state=stepFailed?'failed':warning?'warning':loading[i]?'loading':button.disabled?'locked':'ready';
      button.setAttribute?.('aria-busy',String(Boolean(loading[i])));
      button.setAttribute?.('aria-current',i===step?'step':'false');
      button.title=loading[i]?(button.disabled?'準備中':'準備中 · この工程へ移動できます'):button.disabled?'前の工程を完了すると開けます':i===4?'準備済みデータをBambu Studioで開く':'この工程を表示';
      if(warning)button.title=canVisitJoints?'分割にエラーがあります。確定済みの部分だけ可動域を確認できます':'分割にエラーがあります。確認できる可動域はまだありません';
      if(i===4&&!canPrepare)button.title=failed?'エラーを解消するとプリント準備へ進めます':'処理がすべて完了するとプリント準備へ進めます';
    });
    if(imagePanel)imagePanel.hidden=step!==0;
    document.documentElement?.setAttribute('data-workflow-step',String(step));
    if(sourceImage){sourceImage.hidden=!job;if(job)sourceImage.src=api+'jobs/'+job.id+'/files/source.png';}
    if(hint)hint.textContent=busy?'処理中 · '+job.message:[job?'元画像を確認できます。':'画像をドロップして制作を始めましょう。','外観を確認して、分割位置を決めましょう。','マーカーを直接編集できます。変更するとジョイントの再加工が必要です。','ジョイントを動かして確認し、プリント準備へ進みましょう。',job?.stage==='print_ready'?'準備完了 · この工程をクリックするとBambu Studioで開きます。':'この工程をクリックすると印刷ファイルを準備し、完了後にBambu Studioで開きます。'][step];
    if(hint&&!busy&&step===2&&job?.background?.stage==='working')hint.textContent='マーカーはそのまま編集できます。ジョイントを先に準備しています。';
    if(hint&&!busy&&step===2&&job?.background?.revision)hint.textContent='マーカーはそのまま編集できます。ジョイント工程は準備済みです。';
    if(hint&&step===3&&(window.SkelePartition?.hasPendingChanges()||(!job?.mechanical_revision&&!job?.background?.revision)))hint.textContent='可動域を準備中です。完了すると加工済みモデルに切り替わります。';
    if(hint&&step===3&&job?.background?.preview&&!job?.background?.revision&&!job?.mechanical_revision)hint.textContent='確定した関節から動かせます。残りのパーツを準備しています。';
    if(hint&&step===3&&job?.previous_motion&&!job?.mechanical_revision&&!job?.background?.revision&&!job?.background?.preview)hint.textContent='前回確定した部分を表示しています。変更に関係する関節は固定し、完了した部分から更新します。';
    const backgroundFailure=['failed','print_failed'].includes(job?.background?.stage);
    if(hint&&backgroundFailure){
      hint.textContent=(job.background.stage==='failed'?'ジョイント加工に失敗：':'プリント準備に失敗：')+(job.background.error||'処理を完了できませんでした。');
    }
    if(hint)hint.dataset.error=String(backgroundFailure);
    if(symmetrySide&&step!==1)symmetrySide.hidden=true;
    if(restoreSymmetry&&step!==1)restoreSymmetry.hidden=true;
    if(partitionButton)partitionButton.hidden=true;
    if(returnToPartition)returnToPartition.hidden=true;
    if(step===1&&job?.manifest&&!busy){if(symmetrySide)symmetrySide.hidden=false;if(restoreSymmetry)restoreSymmetry.hidden=!job.appearance_symmetry?.active;}
  }
  const active=new Set(['queued','starting','preparing','generating','analysing','paused','symmetrizing','partitioning','machining','printing']);
  const generation=new Set(['queued','starting','preparing','generating','analysing','paused']);
  const requestedJob=new URLSearchParams(window.location?.search||'').get('job');let initialResolved=false;
  const api='../api/';
  function remember(){
    if(!window.history?.replaceState)return;
    const query=new URLSearchParams();
    if(modelSelect.value.startsWith('job:'))query.set('job',modelSelect.value.slice(4));else query.set('model',modelSelect.value);
    window.history.replaceState(null,'','?'+query.toString());
  }
  function message(text){line.textContent=text;line.hidden=!text;}
  function uploadMessage(text){message(text);const feedback=document.getElementById('workflowImageMessage');if(feedback){feedback.textContent=text;feedback.hidden=!text;}}
  function duration(seconds){seconds=Math.max(0,Math.round(seconds||0));const minutes=Math.floor(seconds/60),rest=seconds%60;return minutes?minutes+'分'+String(rest).padStart(2,'0')+'秒':rest+'秒';}
  function showProgress(job){
    const visible=Boolean(job?.progress&&modelSelect.value==='job:'+job.id);progressBox.hidden=!visible;if(!visible)return;
    progressBar.value=job.progress.value;progressText.textContent=(job.stage==='paused'?'一時停止中 · ':'')+job.progress.label+' '+job.progress.percent+'% · 残り約'+duration(job.progress.remaining_seconds)+' · 経過'+duration(job.progress.elapsed_seconds);
    progressBox.title=job.progress.estimate_basis||'';
  }
  function controls(){
    const job=jobs.get(modelSelect.value.replace(/^job:/,''));
    const controlling=Boolean(job&&generation.has(job.stage)&&!job.mechanical_revision);
    if(pauseButton){pauseButton.hidden=!controlling;pauseButton.disabled=false;const paused=job?.stage==='paused';pauseButton.textContent=paused?'▶':'Ⅱ';pauseButton.setAttribute?.('aria-label',paused?'3D生成を再開':'3D生成を一時停止');pauseButton.ariaLabel=paused?'3D生成を再開':'3D生成を一時停止';pauseButton.title=paused?'再開':'一時停止';}
    if(stopButton){stopButton.hidden=!controlling;stopButton.disabled=false;}
    const appearanceEditable=Boolean(job&&['appearance_ready','partition_failed','symmetry_failed'].includes(job.stage)&&!job.mechanical_revision&&!window.SkelePartition?.hasPendingChanges());
    if(symmetrySide){symmetrySide.hidden=!appearanceEditable;symmetrySide.disabled=false;}
    if(restoreSymmetry){restoreSymmetry.hidden=!(appearanceEditable&&job.appearance_symmetry?.active);restoreSymmetry.disabled=false;}
    if(partitionButton)partitionButton.hidden=!(job&&['appearance_ready','partition_failed'].includes(job.stage)&&!job.mechanical_revision&&!window.SkelePartition?.isActive());
    if(returnToPartition)returnToPartition.hidden=!(job&&['mechanical_review','machining_failed','print_failed','print_ready'].includes(job.stage)&&job.partition_revision);
    if(printState){
      const preparing=job&&job.mechanical_revision&&(job.stage==='queued'||job.stage==='printing');
      const failed=job?.stage==='print_failed';
      printState.hidden=!(preparing||failed);
      printState.dataset.state=failed?'failed':'working';
      printState.textContent=failed?'プリント準備に失敗':preparing?'プリント準備中…':'';
    }
    stepControls(job);
  }
  async function request(path,options={}){
    const response=await fetch(api+path,{cache:'no-store',...options});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'処理に失敗しました');return data;
  }
  function apply(job,autoLoad=true){
    jobs.set(job.id,job);
    if(pendingOpen?.id===job.id){
      if(job.mechanical_revision!==pendingOpen.revision||job.stage==='print_failed')pendingOpen=null;
      else if(job.stage==='print_ready'){pendingOpen=null;void openPrepared(job);}
    }
    window.SkelePartition?.jobUpdated(job);
    const value='job:'+job.id;
    let option=Array.from(modelSelect.options).find(o=>o.value===value);
    if(!option){option=document.createElement('option');option.value=value;modelSelect.prepend(option);}
    option.textContent=job.name+' · '+(job.preview_part_count>1?'分割候補':job.manifest?'外観':'生成中');
    if(job.stage==='failed'||job.stage==='interrupted'||job.stage==='cancelled')option.textContent=job.name+' · 処理停止';
    if(job.stage==='paused')option.textContent=job.name+' · 一時停止中';
    if(job.mechanical_revision)option.textContent=job.name+' · '+(job.stage==='print_ready'?'印刷準備完了':'可動確認');
    option.dataset.description=job.message;
    option.dataset.thumbnail='../api/jobs/'+job.id+'/files/source.png';
    if(modelSelect.value===value){
      if(viewedStep===null||viewedStep>=3||job.error)message(job.message+(job.error?' '+job.error:''));
      showProgress(job);
      const revision=viewRevision(job);
      const deferManifest=window.SkelePartition?.shouldDeferManifest(job);
      if(autoLoad&&viewedStep!==0&&job.manifest&&lastLoaded!==revision&&!deferManifest){
        lastLoaded=revision;
        loadModel(value);
      }
    }
    controls();window.SkeleModelGallery?.refresh();if(modelSelect.value!==value&&progressBox&&!jobs.get(modelSelect.value.replace(/^job:/,''))?.progress)progressBox.hidden=true;
    if(modelSelect.value===value)void prefetchStages(job);
  }
  async function uploadFile(file){
    if(uploading)return;
    if(!['image/png','image/jpeg','image/webp'].includes(file.type)){uploadMessage('PNG・JPEG・WebPの画像を選んでください。');return;}
    if(file.size>20*1024*1024){uploadMessage('画像は20 MB以内にしてください。');return;}
    uploading=true;if(upload)upload.disabled=true;uploadMessage('画像を取り込んでいます…');
    try{
      token=(await request('session')).token;
      const job=await request('jobs',{method:'POST',headers:{'Content-Type':file.type,'X-SkeleCAD-Token':token,'X-Image-Name':encodeURIComponent(file.name)},body:file});
      apply(job);modelSelect.value='job:'+job.id;lastLoaded=null;showProgress(job);controls();remember();window.SkeleModelGallery?.refresh();
      // Clear the previous animal immediately: it must not masquerade as the new inference.
      releaseMesh();updatePartState();canvas.dataset.model='';canvas.dataset.loaded='false';requestRender();
      status.hidden=true;uploadMessage(job.message);
    }catch(error){uploadMessage(error.message);}
    finally{uploading=false;if(upload)upload.disabled=false;input.value='';}
  }
  async function ensureEditable(id){
    let job=jobs.get(id);if(!job)throw new Error('モデルが見つかりません');
    if(!job.mechanical_revision)return job;
    token=(await request('session')).token;
    const restored=await request('jobs/'+id+'/repartition',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},body:'{}'});
    const step=viewedStep;apply(restored,false);viewedStep=step;lastLoaded=restored.manifest+':'+restored.manifest_sha256;controls();
    return restored;
  }
  symmetrySide?.addEventListener('change',async()=>{
    let job=jobs.get(modelSelect.value.replace(/^job:/,''));const sourceSide=symmetrySide.value;symmetrySide.value='';
    if(!job||!sourceSide)return;
    symmetrySide.disabled=true;window.SkelePartition?.end?.();message('左右対称化を開始します…');
    try{
      job=await ensureEditable(job.id);
      token=(await request('session')).token;
      apply(await request('jobs/'+job.id+'/symmetry',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},
        body:JSON.stringify({manifest_sha256:job.manifest_sha256,source_side:sourceSide})}));
    }catch(error){message(error.message);}
    finally{symmetrySide.disabled=false;controls();}
  });
  restoreSymmetry?.addEventListener('click',async()=>{
    let job=jobs.get(modelSelect.value.replace(/^job:/,''));if(!job)return;
    restoreSymmetry.disabled=true;message('左右対称化前の形状へ戻しています…');
    try{
      token=(await request('session')).token;
      job=await ensureEditable(job.id);
      const restored=await request('jobs/'+job.id+'/restore-symmetry',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},body:'{}'});
      lastLoaded=null;apply(restored);
    }catch(error){message(error.message);}
    finally{restoreSymmetry.disabled=false;controls();}
  });
  async function prepareAndOpen(job){
    if(preparing||opening)return;
    if(job.stage==='print_ready')return openPrepared(job);
    const review=motion?.reviewState();
    if(!['mechanical_review','print_failed'].includes(job.stage)||!review?.ready||review.collision!=='clear'){
      message('ジョイント工程で食い込みがないことを確認してから、プリント準備を押してください。');return;
    }
    preparing=true;controls();message('印刷ファイルを準備します。完了後にBambu Studioで開きます。');
    pendingOpen={id:job.id,revision:job.mechanical_revision};
    try{
      token=(await request('session')).token;
      apply(await request('jobs/'+job.id+'/print',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},
        body:JSON.stringify({manifest_sha256:job.manifest_sha256,accepted:true,review})}));
    }catch(error){pendingOpen=null;message(error.message);}
    finally{preparing=false;controls();}
  }
  async function openPrepared(job){
    if(opening||job.stage!=='print_ready')return;
    opening=true;controls();message('Bambu Studioを開いています…');
    try{
      token=(await request('session')).token;
      await request('jobs/'+job.id+'/open-print',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},body:JSON.stringify({manifest_sha256:job.manifest_sha256})});
      message('準備済みの印刷ファイルをBambu Studioで開きました。');
    }catch(error){message(error.message);}
    finally{opening=false;controls();}
  }
  input.addEventListener('change',()=>{if(input.files[0])uploadFile(input.files[0]);});
  stepButtons.forEach((button,index)=>button?.addEventListener('click',async()=>{
    const i=index===4?3:index;
    const job=jobs.get(modelSelect.value.replace(/^job:/,''));if(button.disabled)return;
    const visit=++navigation;
    const alreadyViewingMotion=(viewedStep??currentStep(job))===3;
    window.SkelePartition?.end?.();viewedStep=i;controls();
    if(job&&i>0){
      if(i===3&&!window.SkelePartition?.hasPendingChanges()&&!job.mechanical_revision&&job.background?.revision){
        try{
          token=(await request('session')).token;
          const ready=await request('jobs/'+job.id+'/machine',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},body:JSON.stringify({manifest_sha256:job.manifest_sha256})});
          apply(ready,false);
          if(visit!==navigation||modelSelect.value!=='job:'+job.id)return;
        }catch(error){message(error.message);return;}
      }
      if(index===4){
        const current=jobs.get(job.id);
        if(current.stage!=='print_ready'&&!alreadyViewingMotion){
          await loadModel('job:'+job.id);
          for(let n=0;n<100&&!motion?.reviewState()?.ready;n++){
            if(visit!==navigation||modelSelect.value!=='job:'+job.id)return;
            await new Promise(resolve=>setTimeout(resolve,50));
          }
        }
        if(visit===navigation&&modelSelect.value==='job:'+job.id)await prepareAndOpen(current);
        return;
      }
      await loadModel('job:'+job.id);if(i===2&&visit===navigation&&modelSelect.value==='job:'+job.id)window.SkelePartition?.begin();
    }
  }));
  pauseButton?.addEventListener('click',async()=>{
    const job=jobs.get(modelSelect.value.replace(/^job:/,''));if(!job||!generation.has(job.stage))return;
    pauseButton.disabled=true;
    try{token=(await request('session')).token;apply(await request('jobs/'+job.id+'/'+(job.stage==='paused'?'resume':'pause'),{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},body:'{}'}));}
    catch(error){message(error.message);}finally{pauseButton.disabled=false;controls();}
  });
  stopButton?.addEventListener('click',async()=>{
    const job=jobs.get(modelSelect.value.replace(/^job:/,''));if(!job||!generation.has(job.stage))return;
    stopButton.disabled=true;
    try{
      token=(await request('session')).token;const stopped=await request('jobs/'+job.id+'/cancel',{method:'POST',headers:{'Content-Type':'application/json','X-SkeleCAD-Token':token},body:'{}'});
      jobs.delete(job.id);const option=Array.from(modelSelect.options).find(item=>item.value==='job:'+job.id);option?.remove?.();
      if(option&&!option.remove){const index=Array.from(modelSelect.options).indexOf(option);if(index>=0)modelSelect.options.splice(index,1);}
      const fallback=Array.from(modelSelect.options).find(item=>!item.value.startsWith('job:'));if(fallback){modelSelect.value=fallback.value;lastLoaded=null;loadModel(fallback.value);remember();}
      progressBox.hidden=true;message(stopped.message);
    }
    catch(error){message(error.message);}finally{stopButton.disabled=false;controls();}
  });
  window.addEventListener('dragenter',e=>{if(!Array.from(e.dataTransfer?.types||[]).includes('Files'))return;e.preventDefault();depth++;drop.hidden=false;});
  window.addEventListener('dragover',e=>{if(Array.from(e.dataTransfer?.types||[]).includes('Files')){e.preventDefault();e.dataTransfer.dropEffect='copy';}});
  window.addEventListener('dragleave',e=>{e.preventDefault();if(--depth<=0){depth=0;drop.hidden=true;}});
  window.addEventListener('drop',e=>{e.preventDefault();depth=0;drop.hidden=true;const files=e.dataTransfer?.files;
    if(files?.length!==1){uploadMessage('画像を1枚ずつドロップしてください。');return;}uploadFile(files[0]);});
  modelSelect.addEventListener('change',()=>{lastLoaded=null;remember();const job=jobs.get(modelSelect.value.replace(/^job:/,''));message(job?.message||'');showProgress(job);controls();});
  window.SkeleCADWorkflow={refreshControls:controls,ensureEditable,
    modelLoaded(){const job=jobs.get(modelSelect.value.replace(/^job:/,''));if((viewedStep??currentStep(job))===2)window.SkelePartition?.begin();void prefetchStages(job);},
    restoreJob(job){apply(job,false);window.SkeleModelGallery?.refresh?.();},
    async manifest(id,isCurrent=()=>true){
      if(!/^[0-9a-f]{32}$/.test(id))throw new Error('モデルIDが不正です');
      const step=viewedStep;
      const job=jobs.get(id)||await request('jobs/'+id);if(!isCurrent())return null;apply(job,false);
      if(!job.manifest)return null;
      const rememberLoaded=()=>{if(modelSelect.value==='job:'+id)lastLoaded=viewRevision(job);};
      if(step===1){
        const appearance=await readManifest(job,'manifest.json');
        if(!isCurrent())return null;
        rememberLoaded();
        window.SkelePartition?.end?.();
        return {schema_version:1,stage:'appearance_ready',parts:[{name:'appearance',path:api+'jobs/'+id+'/files/appearance.stl',sha256:appearance.geometry?.sha256,color:'#d6c7a8'}],joints:[]};
      }
      if(step===3&&!window.SkelePartition?.hasPendingChanges()&&!job.mechanical_revision&&job.background?.revision){
        const prepared=await readManifest({...job,manifest_sha256:job.background.manifest_sha256},'r_'+job.background.revision+'.json');
        if(!isCurrent())return null;
        rememberLoaded();window.SkelePartition?.end?.();return prepared;
      }
      if(step===3&&!window.SkelePartition?.hasPendingChanges()&&!job.mechanical_revision&&job.background?.preview){
        const preview=job.background.preview;
        const partial=await readManifest({...job,manifest_sha256:preview.manifest_sha256},'v_'+preview.revision+'.json');
        if(!isCurrent())return null;
        const retained=job.previous_motion?await retainedMotion(job,isCurrent):null;
        if(!isCurrent())return null;
        // A failed final audit cannot establish which partial geometry is safe to move.
        if(job.background.stage==='failed'){
          rememberLoaded();window.SkelePartition?.end?.();
          return retained||{...partial,joints:partial.joints.map(j=>({...j,motion_ready:false}))};
        }
        const available=new Set(partial.joints.filter(j=>j.motion_ready!==false).map(j=>j.name));
        const preserve=retained?.joints.some(j=>j.motion_ready!==false&&!available.has(j.name));
        rememberLoaded();window.SkelePartition?.end?.();return preserve?retained:partial;
      }
      if(step===3&&job.previous_motion&&(window.SkelePartition?.hasPendingChanges()||!job.mechanical_revision)){
        const retained=await retainedMotion(job,isCurrent);if(!isCurrent())return null;
        rememberLoaded();window.SkelePartition?.end?.();return retained;
      }
      if(step===3&&(window.SkelePartition?.hasPendingChanges()||!job.mechanical_revision)){
        const preview=await readManifest(job,'manifest.json');
        if(!isCurrent())return null;
        rememberLoaded();window.SkelePartition?.end?.();return {...preview,joints:[]};
      }
      if(step===2&&job.mechanical_revision){
        const preview=await readManifest(job,'manifest.json');
        if(!isCurrent())return null;
        rememberLoaded();
        window.SkelePartition?.load(job,preview);return {...preview,joints:[]};
      }
      const filename=job.manifest.split('/').pop();
      if(!/^(manifest|r_[0-9a-f]{32})\.json$/.test(filename))throw new Error('モデル参照が不正です');
      const manifest=await readManifest(job,filename);if(!isCurrent())return null;rememberLoaded();window.SkelePartition?.load(job,manifest);controls();return manifest;
    }
  };
  async function refresh(){
    try{const data=await request('jobs');for(const job of data.jobs)apply(job);
      if(!initialResolved){initialResolved=true;
        if(requestedJob&&jobs.has(requestedJob)){modelSelect.value='job:'+requestedJob;lastLoaded=null;apply(jobs.get(requestedJob));
          if(!jobs.get(requestedJob).manifest)loadModel(modelSelect.value);}
      }
    }
    catch(error){if(Array.from(jobs.values()).some(j=>active.has(j.stage)))message('生成状態を取得できません。接続を再確認しています。');}
    setTimeout(refresh,2000);
  }
  refresh();
})();
