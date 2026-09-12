/* Touch gestures share the existing partition actions; no extra controls. */
"use strict";
(()=>{
  const media=window.matchMedia('(max-width: 760px), (max-width: 1024px) and (pointer: coarse), (max-width: 1024px) and (max-height: 500px)');
  const root=document.documentElement,canvas=document.getElementById('gl'),touches=new Map();
  const holdMs=600,tapMs=300,slop=8;
  let pending=null,lastTap=null,lastTouch=-Infinity;
  const surface=target=>target===canvas?canvas:target.closest?.('.partitionMarker');
  const editing=()=>root.getAttribute('data-workflow-step')==='2'&&window.SkelePartition?.isActive();
  function cancel(){if(pending)clearTimeout(pending.timer);pending=null;lastTap=null;}
  document.addEventListener('pointerdown',e=>{
    if(e.pointerType!=='touch')return;
    lastTouch=Date.now();touches.set(e.pointerId,true);
    if(touches.size!==1){cancel();return;}
    const target=surface(e.target);
    if(!target||!editing()){cancel();return;}
    e.preventDefault();
    const gesture={id:e.pointerId,x:e.clientX,y:e.clientY,target,name:target.dataset.markerName,time:Date.now(),fired:false};
    if(pending)clearTimeout(pending.timer);
    pending=gesture;
    if(target!==canvas)target.setPointerCapture(e.pointerId);
    gesture.timer=setTimeout(()=>{
      if(pending!==gesture||touches.size!==1||!editing())return;
      gesture.fired=true;lastTap=null;
      if(gesture.name)window.SkelePartition.removeNamed(gesture.name);
      else window.SkelePartition.addAt(gesture.x,gesture.y);
    },holdMs);
  },{capture:true,passive:false});
  document.addEventListener('pointermove',e=>{
    if(!pending||pending.id!==e.pointerId)return;
    if(Math.hypot(e.clientX-pending.x,e.clientY-pending.y)>slop)cancel();
  },true);
  for(const type of ['pointerup','pointercancel','lostpointercapture'])document.addEventListener(type,e=>{
    touches.delete(e.pointerId);
    if(!pending||pending.id!==e.pointerId)return;
    const gesture=pending;clearTimeout(gesture.timer);pending=null;
    if(type!=='pointerup'||gesture.fired||!editing()||Math.hypot(e.clientX-gesture.x,e.clientY-gesture.y)>slop){lastTap=null;return;}
    const now=Date.now();
    if(!gesture.name||now-gesture.time>tapMs){lastTap=null;return;}
    if(lastTap&&lastTap.name===gesture.name&&now-lastTap.time<=tapMs&&Math.hypot(e.clientX-lastTap.x,e.clientY-lastTap.y)<=20){
      lastTap=null;window.SkelePartition.toggleNamed(gesture.name);
    }else lastTap={name:gesture.name,time:now,x:e.clientX,y:e.clientY};
  },true);
  // Suppress native long-press menus and synthesized mouse gestures after touch.
  for(const type of ['contextmenu','dblclick','click'])document.addEventListener(type,e=>{
    if(surface(e.target)&&(e.pointerType==='touch'||Date.now()-lastTouch<1000)){
      e.preventDefault();e.stopImmediatePropagation();
    }
  },true);
  document.addEventListener('selectstart',e=>{
    if(media.matches&&!e.target.closest?.('input,textarea,[contenteditable="true"]'))e.preventDefault();
  });
  document.getElementById('modelSelect').addEventListener('change',cancel);
  let lastStep=root.getAttribute('data-workflow-step');
  new MutationObserver(()=>{const step=root.getAttribute('data-workflow-step');if(step!==lastStep){cancel();lastStep=step;}}).observe(root,{attributes:true,attributeFilter:['data-workflow-step']});
  document.addEventListener('visibilitychange',()=>{cancel();touches.clear();});
  window.addEventListener('blur',()=>{cancel();touches.clear();});
  media.addEventListener('change',()=>{cancel();window.SkeleViewer?.requestRender();});
  window.SkeleMobile={isActive:()=>media.matches};
})();
/* The same help entry point explains touch or mouse actions for the current step. */
(()=>{
  const byId=id=>document.getElementById(id),button=byId('workflowHelpOpen'),dialog=byId('workflowHelp');
  if(!button||!dialog)return;
  let renderedKey='';
  function refresh(){
    const printLabel=window.SkeleCADWorkflow?.printLabel?.()||'プリント準備';
    const titles=['画像','モデル','パーツ分割','可動域',printLabel];
    const printHelp=printLabel==='プリント開始'?['「プリント開始」を押すと印刷用データを準備し、確認画面に印刷先とプレートを表示します。','プレートとフィラメントを確認し、「印刷を開始」を押すとプリンターで印刷が始まります。複数プレートは1枚ずつ開始してください。']:['「プリント準備」を押すと印刷用データを準備します。処理中は下部に進み具合が表示されます。','準備ができると、SkeleCADを動かしているPCのBambu Studioで開きます。スマホ上では開きません。'];
    const raw=Number(document.documentElement.getAttribute('data-workflow-step')||0),step=raw>=0&&raw<5?raw:0;
    const touch=window.SkeleMobile?.isActive(),key=step+':'+touch+':'+printLabel;
    if(key===renderedKey)return;renderedKey=key;
    const view=touch?'背景を1本指でドラッグすると視点が回転します。2本指で平行移動、ピンチで拡大・縮小、ひねると視点が傾きます。':'背景をドラッグすると視点が回転します。ホイールで拡大・縮小、中ボタンドラッグで平行移動できます。';
    const instructions=[
      [touch?'画像エリアをタップし、写真ライブラリやファイルから画像を選びます。':'画像を画面へドラッグ＆ドロップして、新しい3Dモデルを作ります。','PNG・JPEG・WebPに対応しています。画像は1枚ずつ、20 MB以内で選んでください。','右上の画像選択から、作成済みのモデルを切り替えられます。'],
      [view,'「左右対称化」で、元の形を使うか、左・右どちらの形に揃えるかを選びます。','形を確認したら「パーツ分割」へ進みます。'],
      [touch?'モデル表面を約0.6秒長押しすると、その位置にマーカーを追加します。':'モデル表面をダブルクリックすると、その位置にマーカーを追加します。',touch?'既存マーカーを長押しすると削除します。左右対称のペアは一緒に削除されます。':'マーカーを右クリックすると削除します。左右対称のペアは一緒に削除されます。',touch?'マーカーをダブルタップすると、左右対称をオン・オフできます。':'マーカーをダブルクリックすると左右対称を切り替えます。マーカー上のホイールで分割範囲を調整できます。','中央付近に追加したマーカーは単独、それ以外は自動で左右対称になります。変更後は色分けとジョイントを更新します。',view],
      [touch?'パーツの中央を指でドラッグすると関節が曲がります。外側を円弧状になぞるとねじれます。':'パーツの中央をドラッグすると関節が曲がります。外側を円弧状にドラッグ、またはShiftを押しながらドラッグするとねじれます。',view,'カメラのカードで姿勢を保存し、保存した画像を選ぶと復元できます。一覧内のドラッグで並べ替えます。一覧から大きく外へドラッグし、「離すと削除」が出たところで放すと削除できます。',touch?'右上のリセットで視点と関節を初期状態に戻します。':'「表示をリセット」で視点と関節を初期状態に戻します。'],
      printHelp
    ];
    byId('workflowHelpTitle').textContent=titles[step]+'の操作';
    const body=byId('workflowHelpBody');body.replaceChildren();
    const list=items=>{const ul=document.createElement('ul');for(const text of items){const li=document.createElement('li');li.textContent=text;ul.append(li);}return ul;};
    body.append(list(instructions[step]));
    // Printing is an action from the motion step, so its help is reachable here too.
    if(step===3){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=printLabel+'について';details.append(summary,list(printHelp));body.append(details);}
    body.scrollTop=0;
  }
  button.addEventListener('click',()=>{refresh();if(!dialog.open)dialog.showModal();});
  byId('workflowHelpClose').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>button.focus({preventScroll:true}));
  dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();});
  new MutationObserver(()=>{if(dialog.open)refresh();}).observe(document.documentElement,{attributes:true,attributeFilter:['data-workflow-step']});
  window.addEventListener('resize',()=>{if(dialog.open)refresh();});
})();

/* Build the loading stroke in the button's own pixel coordinates. */
(()=>{
  const buttons=[0,1,2,3,4].map(i=>document.getElementById('step'+i)).filter(Boolean);
  if(!buttons.length)return;
  const ns='http://www.w3.org/2000/svg';
  const outlines=buttons.map((button,index)=>{
    const svg=document.createElementNS(ns,'svg');svg.setAttribute('class','workflowLoadingOutline');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');
    const paths=['workflowLoadingGlow','workflowLoadingTrail'].map(name=>{const path=document.createElementNS(ns,'path');path.setAttribute('class',name);path.setAttribute('pathLength','100');svg.append(path);return path;});
    button.append(svg);return {button,index,svg,paths};
  });
  function resize(){
    for(const {button,index,svg,paths} of outlines){
      const {width:w,height:h}=button.getBoundingClientRect();if(!w||!h)continue;
      const style=getComputedStyle(button),n=parseFloat(style.getPropertyValue('--workflow-notch'))||12,r=parseFloat(style.getPropertyValue('--workflow-corner'))||8;
      const start=index===0?`M ${r} 2`:'M 3 2';
      const right=index===4?`H ${w-r} Q ${w-2} 2 ${w-2} ${r} V ${h-r} Q ${w-2} ${h-2} ${w-r} ${h-2}`:`H ${w-n-1} L ${w-3} ${h/2} L ${w-n-1} ${h-2}`;
      const left=index===0?`H ${r} Q 2 ${h-2} 2 ${h-r} V ${r} Q 2 2 ${r} 2 Z`:`H 3 L ${n+2} ${h/2} Z`;
      svg.setAttribute('viewBox',`0 0 ${w} ${h}`);for(const path of paths)path.setAttribute('d',start+' '+right+' '+left);
    }
  }
  const observer=new ResizeObserver(resize);for(const button of buttons)observer.observe(button);
  window.addEventListener('resize',resize);resize();
})();
