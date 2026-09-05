"""Read-only G-code inspection renderer; no desktop slicer or printer access."""
import argparse,math,re,zipfile,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

def segments(code):
    body=code.split('; CHANGE_LAYER',1)[1].split('; filament end gcode',1)[0]
    xyz=np.zeros(3);feature='Unknown';layer=0;result=[]
    for line in body.splitlines():
        if line.startswith('; CHANGE_LAYER'):layer+=1
        if line.startswith('; FEATURE: '):feature=line[11:].strip()
        command=line.split(';',1)[0].strip()
        if not re.match(r'G[0123] ',command):continue
        fields={k:float(v) for k,v in re.findall(r'([XYZIJE])(-?(?:\d+(?:\.\d*)?|\.\d+))',command)}
        end=np.array([fields.get(k,xyz[i]) for i,k in enumerate('XYZ')])
        if fields.get('E',0)>0 and ('X' in fields or 'Y' in fields):
            points=[xyz.copy(),end.copy()]
            if command.startswith(('G2 ','G3 ')) and ('I' in fields or 'J' in fields):
                center=xyz[:2]+[fields.get('I',0),fields.get('J',0)]
                radius=np.linalg.norm(xyz[:2]-center)
                a=math.atan2(*(xyz[:2]-center)[::-1]);b=math.atan2(*(end[:2]-center)[::-1])
                direction=1 if command.startswith('G3 ') else -1
                sweep=((b-a)*direction)%(2*math.pi)
                angles=a+direction*np.linspace(0,sweep,max(2,int(radius*sweep/.3)+1))
                points=[np.array([*(center+radius*np.array([math.cos(t),math.sin(t)])),end[2]]) for t in angles]
            for a,b in zip(points,points[1:]):result.append((a,b,feature,layer))
        xyz=end
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    with zipfile.ZipFile(args.package) as z:code=z.read('Metadata/plate_1.gcode').decode()
    lines=segments(code);im=Image.new('RGB',(1500,1000),'#181e27');d=ImageDraw.Draw(im)
    d.text((25,15),args.package.name,fill='white')
    d.text((25,38),'G-code extrusion paths | White: model   Orange: support   Green: brim/skirt | Not a physical fit test',fill='#cad5df')
    panels=[('TOP / ALL LAYERS',np.array([[1,0,0],[0,1,0]]),False),('FRONT',np.array([[1,0,0],[0,0,1]]),False),
            ('ISOMETRIC',np.array([[.707,-.707,0],[.354,.354,.866]]),False),('FIRST LAYER',np.array([[1,0,0],[0,1,0]]),True)]
    for i,(title,R,first) in enumerate(panels):
        x=(i%2)*750;y=70+(i//2)*460
        subset=[s for s in lines if not first or s[3]==0]
        points=np.array([p for s in subset for p in s[:2]])@R.T
        lo=points.min(0);hi=points.max(0);scale=min(690/max(hi[0]-lo[0],1),390/max(hi[1]-lo[1],1))
        offset=np.array([x+375,y+235])
        d.text((x+25,y+10),title,fill='white');d.rectangle((x+10,y+30,x+740,y+450),outline='#3a4859')
        for a,b,feature,layer in subset:
            projected=(np.array([a,b])@R.T-(lo+hi)/2)*[scale,-scale]+offset
            color='#ffaf52' if 'Support' in feature else '#65cc87' if feature in ('Skirt','Brim','Skirt/Brim') else '#e3e8ee'
            d.line([tuple(p) for p in projected],fill=color,width=1)
    args.output.parent.mkdir(parents=True,exist_ok=True);im.save(args.output)
    counts={f:sum(s[2]==f for s in lines) for f in sorted({s[2] for s in lines})}
    args.output.with_suffix('.json').write_text(json.dumps({'features':counts,'source':str(args.package),'layers':max(s[3] for s in lines)+1},indent=2),encoding='utf-8')
    print(args.output)
if __name__=='__main__':main()
