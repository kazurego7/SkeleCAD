const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
  constructor(tag='div'){this.tag=tag;this.dataset={};this.children=[];this.handlers={};this.textContent='';this.value='';this.options=[];this.open=false;this.hidden=false;this.disabled=false;this.className='';}
  addEventListener(type,fn){(this.handlers[type]||=[]).push(fn);}
  dispatchEvent(event){for(const fn of this.handlers[event.type]||[])fn(event);}
  append(...values){this.children.push(...values);}
  replaceChildren(...values){this.children=[...values];}
  setAttribute(name,value){this[name]=value;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  closest(selector){return selector.startsWith('.')&&this.className.split(' ').includes(selector.slice(1))?this:null;}
}
const names=['modelSelect','modelPicker','modelGallery','modelGalleryList','modelGalleryClose','modelGalleryTitle','modelTrashOpen','modelTrashBack','modelTrashEmpty','modelGalleryStatus','gl'];
const ids=new Map(names.map(id=>[id,new Element()])),jobId='a'.repeat(32);
const select=ids.get('modelSelect');select.value='job:'+jobId;select.options=[
  {value:'job:'+jobId,textContent:'飛竜A',dataset:{description:'可動確認',thumbnail:'../api/jobs/'+jobId+'/files/source.png'}},
  {value:'../built-in.stl',textContent:'標準モデル',dataset:{description:'保護対象',thumbnail:'../preview.png'}}
];
ids.get('gl').dataset.loaded='true';
const stored=new Map(),localStorage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)};
const document={getElementById:id=>ids.get(id),createElement:tag=>new Element(tag)};
let trashJobs=[],emptyCalls=0;
const response=value=>Promise.resolve({ok:true,json:()=>Promise.resolve(value)});
const fetch=(url,options={})=>{
  if(url.endsWith('/session'))return response({token:'test-token'});
  if(url.endsWith('/trash')&&(!options.method||options.method==='GET'))return response({jobs:trashJobs});
  if(url.includes('/jobs/')&&url.endsWith('/trash')){trashJobs=[{id:jobId,name:'飛竜A',stage:'appearance_ready',message:'外観の生成完了'}];return response(trashJobs[0]);}
  if(url.endsWith('/restore')){const job=trashJobs[0];trashJobs=[];return response(job);}
  if(url.endsWith('/trash/empty')){emptyCalls++;const deleted=trashJobs.map(job=>job.id);trashJobs=[];return response({deleted,count:deleted.length});}
  throw new Error('unexpected fetch '+url);
};
const window={SkeleViewer:{capturePreview:()=> 'data:image/jpeg;base64,current'}};
window.SkeleCADWorkflow={restoreJob(job){select.options.push({value:'job:'+job.id,textContent:job.name,dataset:{thumbnail:'../api/jobs/'+job.id+'/files/source.png'}});}};
const context=vm.createContext({document,window,localStorage,fetch,Event:class{constructor(type,options){this.type=type;Object.assign(this,options);}},module:{exports:{}},console,Object,Array,String,JSON});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../model-gallery.js'),'utf8'),context);
const gallery=window.SkeleModelGallery,list=ids.get('modelGalleryList');
(async()=>{
  assert.equal(ids.get('modelPicker').textContent,'飛竜A');
  ids.get('modelPicker').handlers.click[0]();
  assert.equal(ids.get('modelGallery').open,true);assert.equal(list.children.length,2);
  assert.equal(list.children[0].children[0].children[0].src,'data:image/jpeg;base64,current','the current model uses a real captured 3D thumbnail');
  assert.equal(list.children[0].children[0].children[1].children.length,1,'model cards show only the title, without workflow descriptions');
  assert.equal(list.children[0].children[1].className,'modelCardTrash','generated jobs have a trash action');
  assert.equal(list.children[1].children.length,1,'built-in models cannot be trashed');
  await list.handlers.click[0]({target:list.children[0].children[1]});
  assert.deepEqual(gallery.items(),['../built-in.stl']);assert.equal(select.value,'../built-in.stl','trashing the selected model selects a safe fallback');
  await ids.get('modelTrashOpen').handlers.click[0]();
  assert.equal(ids.get('modelGalleryTitle').textContent,'ゴミ箱');
  const restore=list.children[0].children[0].children[1].children[1];assert.equal(restore.textContent,'復元','restore sits in the same footer row as the title');
  assert.equal(list.children[0].children[0].children[1].children.length,2,'trash cards omit workflow descriptions');
  await list.handlers.click[0]({target:restore});
  assert.equal(list.children[0].textContent,'ゴミ箱は空です');
  ids.get('modelTrashBack').handlers.click[0]();assert.equal(gallery.items().length,2,'restored models return to the main gallery');
  trashJobs=[{id:jobId,name:'飛竜A',stage:'appearance_ready'}];
  await ids.get('modelTrashOpen').handlers.click[0]();await ids.get('modelTrashEmpty').handlers.click[0]();
  assert.equal(emptyCalls,1);assert.equal(list.children[0].textContent,'ゴミ箱は空です');assert.equal(ids.get('modelTrashEmpty').hidden,true);
  console.log('PASS: model gallery trash, protected built-ins, restore and empty-trash actions');
})().catch(error=>{console.error(error);process.exitCode=1;});
