/* Parse and hash off the UI thread; transfer arrays instead of copying them. */
"use strict";
function normalize(v){const n=Math.hypot(...v)||1;return v.map(x=>x/n);}
function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function parseSTL(buffer){
  if(buffer.byteLength<84)throw new Error('STLファイルが短すぎます');
  const view=new DataView(buffer),count=view.getUint32(80,true);
  if(!count||84+count*50!==buffer.byteLength)throw new Error('バイナリSTLを読み取れません');
  const positions=new Float32Array(count*9),normals=new Float32Array(count*9),low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity];
  for(let f=0;f<count;f++){
    const offset=84+f*50;
    let normal=[0,1,2].map(k=>view.getFloat32(offset+k*4,true));
    for(let j=0;j<3;j++)for(let k=0;k<3;k++){
      const value=view.getFloat32(offset+12+j*12+k*4,true);
      if(!Number.isFinite(value))throw new Error('モデルの座標が不正です');
      positions[f*9+j*3+k]=value;low[k]=Math.min(low[k],value);high[k]=Math.max(high[k],value);
    }
    if(!normal.every(Number.isFinite)||Math.hypot(...normal)<1e-10){
      const a=positions.slice(f*9,f*9+3),b=positions.slice(f*9+3,f*9+6),c=positions.slice(f*9+6,f*9+9);
      normal=normalize(cross(Array.from(b,(v,k)=>v-a[k]),Array.from(c,(v,k)=>v-a[k])));
    }
    for(let j=0;j<3;j++)normals.set(normal,f*9+j*3);
  }
  return {positions,normals,low,high};
}

self.onmessage=async({data})=>{
  try{
    const response=await fetch(data.url,{cache:'no-cache'});
    if(!response.ok)throw new Error('読み込みエラー '+response.status);
    const bytes=await response.arrayBuffer();
    const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    if(data.sha256&&data.sha256!==sha256)throw new Error('生成データの照合に失敗しました');
    const mesh=parseSTL(bytes);
    self.postMessage({id:data.id,mesh,sha256},[mesh.positions.buffer,mesh.normals.buffer]);
  }catch(error){self.postMessage({id:data.id,error:error.message});}
};
