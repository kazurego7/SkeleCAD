const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
let width=78.2,height=48,notch=10,corner=7,resize;
function node(){return {attrs:{},children:[],setAttribute(k,v){this.attrs[k]=v;},append(n){this.children.push(n);},getBoundingClientRect(){return {width,height};}};}
const buttons=Array.from({length:5},node),observed=[];
const source=fs.readFileSync(path.join(__dirname,'../mobile-ui.js'),'utf8');
vm.runInNewContext(source.slice(source.indexOf('/* Build the loading stroke')),{document:{getElementById:id=>buttons[Number(id.slice(4))],createElementNS:node},getComputedStyle:()=>({getPropertyValue:k=>String(k==='--workflow-notch'?notch:corner)}),ResizeObserver:class{constructor(fn){resize=fn;}observe(n){observed.push(n);}},window:{addEventListener(){}}});
function verify(){
 for(const button of buttons){assert.equal(button.children.length,1);const svg=button.children[0];assert.equal(svg.attrs['aria-hidden'],'true');assert.equal(svg.attrs.viewBox,`0 0 ${width} ${height}`);assert.equal(svg.children.length,2);
  const d=svg.children[0].attrs.d;assert.equal(d,svg.children[1].attrs.d);assert.match(d,/Z$/);assert.doesNotMatch(d,/NaN|Infinity/);
  for(const command of d.matchAll(/([MLHVQ])([^MLHVQZ]+)/g)){const values=command[2].trim().split(/\s+/).map(Number);for(let i=0;i<values.length;i++){const bound=command[1]==='H'?width:command[1]==='V'?height:i%2?height:width;assert.ok(Number.isFinite(values[i])&&values[i]>=0&&values[i]<=bound);}}
  assert.equal(svg.children[0].attrs.pathLength,'100');
 }
}
assert.equal(observed.length,5);verify();
const phone=buttons[2].children[0].children[0].attrs.d;
width=130;height=44;notch=12;corner=8;resize();verify();assert.notEqual(buttons[2].children[0].children[0].attrs.d,phone);
width=92;height=63;notch=10;corner=7;resize();verify();
console.log('PASS: closed arrow outlines fit all five buttons and resize across phone, desktop and landscape dimensions');
