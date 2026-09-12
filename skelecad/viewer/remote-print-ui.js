'use strict';
(()=>{
  const byId=id=>document.getElementById(id),dialog=byId('remotePrintConfirm');
  const start=byId('remotePrintStart'),cancel=byId('remotePrintCancel'),status=byId('remotePrintStatus');
  const plate=byId('remotePrintPlate'),bed=byId('remotePrintBedClear');
  let run=0,current=null;
  async function request(path,body){
    const options={cache:'no-store'};
    if(body){
      const response=await fetch('../api/session',{cache:'no-store'}),session=await response.json();
      options.method='POST';options.headers={'Content-Type':'application/json','X-SkeleCAD-Token':session.token};options.body=JSON.stringify(body);
    }
    const response=await fetch('../api/'+path,options),data=await response.json();
    if(!response.ok)throw new Error(data.error||'印刷の処理に失敗しました。');return data;
  }
  function controls(){start.disabled=!current||current.data.stage!=='ready'||!bed.checked||!current.isCurrent();}
  function show(data){
    current.data=data;status.textContent=data.message;
    cancel.textContent=data.stage==='sending'?'送信を中止':(['preparing','ready'].includes(data.stage)?'キャンセル':'閉じる');
    if(data.stage==='ready'){
      plate.replaceChildren();
      for(const p of data.plates){const option=document.createElement('option');option.value=String(p.plate);option.textContent='プレート'+p.plate+' · 約'+Math.ceil(p.seconds/60)+'分 · '+p.grams.toFixed(1)+'g';plate.append(option);}
      plate.disabled=false;
      byId('remotePrintModel').textContent=current.job.name+' / '+data.printer+' / '+data.filament;
    }
    controls();
  }
  async function poll(id,jobId,ticket){
    while(id===run&&dialog.open){
      const data=await request('jobs/'+jobId+'/remote-print/'+ticket);
      if(id!==run||!dialog.open)return;
      show(data);
      if(!['preparing','sending'].includes(data.stage))return;
      await new Promise(resolve=>setTimeout(resolve,1500));
    }
  }
  bed.addEventListener('change',controls);
  async function cancelOrClose(){
    const item=current,id=run;
    if(item?.data.ticket&&['preparing','ready','sending'].includes(item.data.stage)){
      cancel.disabled=true;
      try{
        const data=await request('jobs/'+item.job.id+'/remote-print/cancel',{ticket:item.data.ticket});
        if(id!==run)return;
        if(data.stage==='sending'){show(data);return;}
      }catch(error){if(id===run)status.textContent=error.message;return;}
      finally{cancel.disabled=false;}
    }
    dialog.close();
  }
  cancel.addEventListener('click',cancelOrClose);
  dialog.addEventListener('cancel',event=>{event.preventDefault();cancelOrClose();});
  dialog.addEventListener('close',()=>{run++;current=null;byId('step4')?.focus?.();});
  start.addEventListener('click',async()=>{
    if(start.disabled||!current||!current.isCurrent())return;
    const item=current,id=run;start.disabled=true;plate.disabled=true;bed.disabled=true;
    item.data.stage='sending';status.textContent='プリンターへ送信しています…';cancel.textContent='送信を中止';
    try{
      const data=await request('jobs/'+item.job.id+'/remote-print/start',{ticket:item.data.ticket,plate:Number(plate.value),accepted:true,bed_clear:bed.checked});
      if(id!==run)return;show(data);await poll(id,item.job.id,data.ticket);
    }catch(error){if(id===run){status.textContent=error.message+' 開始結果が不明な場合は、プリンター本体を確認してください。';item.data.stage='unknown';controls();}}
  });
  window.SkeleRemotePrint={async open(job,review,isCurrent){
    if(dialog.open)return;
    const id=++run;current={job,isCurrent,data:{stage:'preparing'}};
    bed.checked=false;bed.disabled=false;plate.disabled=true;plate.replaceChildren();start.disabled=true;cancel.disabled=false;cancel.textContent='キャンセル';
    byId('remotePrintModel').textContent=job.name;status.textContent='印刷データを準備しています…';dialog.showModal();
    try{
      const data=await request('jobs/'+job.id+'/remote-print/prepare',{manifest_sha256:job.manifest_sha256,review});
      if(id!==run)return;show(data);await poll(id,job.id,data.ticket);
    }catch(error){if(id===run){current.data.stage='failed';status.textContent=error.message;controls();}}
  }};
})();
