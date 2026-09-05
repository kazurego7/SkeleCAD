"""Lightweight orthographic point-surface review with millimetre grid."""
import argparse
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image, ImageDraw

p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
m=trimesh.load_mesh(a.input);v=m.vertices;n=m.vertex_normals
sheet=Image.new('RGB',(1320,760),'#f7f7f4');draw=ImageDraw.Draw(sheet)
for title,axes,sign,region in [('Left side X/Z',(0,2,1),1,(10,10,850,360)),('Right side X/Z',(0,2,1),-1,(10,390,850,360)),('Front Y/Z',(1,2,0),-1,(890,10,410,720))]:
    x,y,w,h=region;u,z,d=axes
    low=v[:,[u,z]].min(0);high=v[:,[u,z]].max(0);scale=min((w-40)/(high[0]-low[0]),(h-40)/(high[1]-low[1]))
    px=((v[:,u]-low[0])*scale+x+20).astype(int);py=(y+h-20-(v[:,z]-low[1])*scale).astype(int)
    order=np.argsort(v[:,d]*sign)
    brightness=np.clip(.45+.55*np.abs(n[:,d]),0,1)
    color=(brightness[:,None]*np.array([156,128,90])).astype(np.uint8)
    arr=np.asarray(sheet).copy()
    for dx,dy in [(0,0),(1,0),(0,1),(1,1)]:arr[py[order]+dy,px[order]+dx]=color[order]
    sheet=Image.fromarray(arr);draw=ImageDraw.Draw(sheet)
    for val in np.arange(np.ceil(low[0]/10)*10,high[0]+1,10):
        gx=x+20+(val-low[0])*scale;draw.line((gx,y+25,gx,y+h-10),fill='#aabfc3',width=1);draw.text((gx,y+h-10),str(int(val)),fill='black')
    for val in np.arange(np.ceil(low[1]/10)*10,high[1]+1,10):
        gy=y+h-20-(val-low[1])*scale;draw.line((x+10,gy,x+w-10,gy),fill='#aabfc3',width=1);draw.text((x,gy),str(int(val)),fill='black')
    draw.text((x+20,y),title,fill='black')
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);sheet.save(out,quality=82)
print(sheet.size,out.stat().st_size)
