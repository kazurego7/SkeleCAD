'use strict';
importScripts('motion-core.js?v=3.4.3');
let parts={},cache=new Map(),ignoredRegions=[];
self.onmessage=function(event){
  const data=event.data;
  try{
    if(data.type==='init'){
      parts={};cache=new Map();ignoredRegions=Array.isArray(data.ignoredRegions)?data.ignoredRegions:[];
      for(const p of data.parts)parts[p.name]={tree:SkeleMotion.buildBVH(p.positions),samples:SkeleMotion.samples(p.positions)};
      self.postMessage({type:'ready'});
    }else if(data.type==='check'){
      const started=performance.now(),result=SkeleMotion.collide(parts,data.matrices,3000,cache,ignoredRegions);
      self.postMessage({type:'result',id:data.id,...result,computeMs:performance.now()-started},[result.points.buffer]);
    }
  }catch(error){self.postMessage({type:'error',message:String(error.message||error)});}
};
