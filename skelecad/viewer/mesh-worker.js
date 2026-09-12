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

function isCompact(buffer){return buffer.byteLength>=8&&new Uint8Array(buffer,0,8).every((v,i)=>i===6?(v===49||v===50):v===[83,75,77,69,83,72,49,0][i]);}
function parseCompact(buffer){
  if(buffer.byteLength<48)throw new Error('表示用データが短すぎます');
  const view=new DataView(buffer),vertices=view.getUint32(8,true),faces=view.getUint32(12,true);
  if(!vertices||!faces||vertices>faces*3||48+vertices*12+faces*12!==buffer.byteLength)throw new Error('表示用データのサイズが不正です');
  const source=new Uint8Array(buffer),tableBytes=new Uint8Array(vertices*12),indexBytes=new Uint8Array(faces*12);
  for(let byte=0;byte<12;byte++){
    for(let v=0;v<vertices;v++)tableBytes[v*12+byte]=source[48+byte*vertices+v];
    for(let f=0;f<faces;f++)indexBytes[f*12+byte]=source[48+vertices*12+byte*faces+f];
  }
  const table=new DataView(tableBytes.buffer),indices=new DataView(indexBytes.buffer);
  const positions=new Float32Array(faces*9),normals=new Float32Array(faces*9),low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity];
  for(let f=0;f<faces;f++){
    for(let j=0;j<3;j++){
      const index=indices.getUint32(f*12+j*4,true);if(index>=vertices)throw new Error('表示用データの頂点参照が不正です');
      for(let k=0;k<3;k++){
        const value=table.getFloat32(index*12+k*4,true);if(!Number.isFinite(value))throw new Error('モデルの座標が不正です');
        positions[f*9+j*3+k]=value;low[k]=Math.min(low[k],value);high[k]=Math.max(high[k],value);
      }
    }
    const offset=f*9,a=[0,1,2].map(k=>positions[offset+3+k]-positions[offset+k]),b=[0,1,2].map(k=>positions[offset+6+k]-positions[offset+k]);
    const normal=normalize(cross(a,b));for(let j=0;j<3;j++)normals.set(normal,offset+j*3);
  }
  return {positions,normals,low,high};
}

self.onmessage=async({data})=>{
  try{
    const url=new URL(data.url,self.location?.href);
    if(data.sha256)url.searchParams.set('sha256',data.sha256);
    url.searchParams.set('cache','shared-scale-20260912');
    if(data.compact)url.searchParams.set('format','mesh-v1');
    if(data.compact&&data.preview)url.searchParams.set('detail','preview-v3');
    const response=await fetch(url.href,{cache:'default'});
    if(!response.ok)throw new Error('読み込みエラー '+response.status);
    const bytes=await response.arrayBuffer();
    let sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    const compact=isCompact(bytes);
    if(compact){
      if(bytes.byteLength<48||response.headers?.get('X-Content-SHA256')!==sha256)throw new Error('表示用データの照合に失敗しました');
      sha256=Array.from(new Uint8Array(bytes,16,32),b=>b.toString(16).padStart(2,'0')).join('');
    }
    if(data.sha256&&data.sha256!==sha256)throw new Error('生成データの照合に失敗しました');
    const mesh=compact?parseCompact(bytes):parseSTL(bytes);
    const detail=compact&&new Uint8Array(bytes)[6]===50?'preview':'full';
    if(detail==='preview'&&!data.preview)throw new Error('精密形状の代わりに軽量形状が返されました');
    self.postMessage({id:data.id,mesh,sha256,detail},[mesh.positions.buffer,mesh.normals.buffer]);
  }catch(error){self.postMessage({id:data.id,error:error.message});}
};
