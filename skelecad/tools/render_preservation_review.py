"""Matched, enlarged anatomical views of the unchanged source and repaired mesh."""
import sys
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from hybrid_context import INPUT, HYBRID, H

source=trimesh.load_mesh(INPUT)
fixed=trimesh.util.concatenate([trimesh.load_mesh(p) for p in sorted((HYBRID/'parts').glob('*.stl'))])
sheet=Image.new('RGB',(1290,840),'#f4f2ec')
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',19)
small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',15)
views=[('Hand / arm',0,(-72,-36),(36,73)),
       ('Foot / inner leg',0,(-50,1),(-3,69)),
       ('Both legs / front',1,(-48,48) if H.get('part_translation_mm') else (-34,34),(-3,69))]
for row,(model,label) in enumerate([(source,'ORIGINAL - before joint machining'),(fixed,'REPAIRED - local joint machining')]):
    draw=ImageDraw.Draw(sheet)
    draw.text((16,row*420+8),label,fill='#202522',font=font)
    for col,(title,axis,ur,zr) in enumerate(views):
        x,y=col*430+10,row*420+65
        width,height=410,344
        centers=model.triangles_center
        mask=(centers[:,axis]>=ur[0])&(centers[:,axis]<=ur[1])&(centers[:,2]>=zr[0])&(centers[:,2]<=zr[1])
        mask &= centers[:,1]>0 if axis==0 else ((centers[:,0]>-50)&(centers[:,0]<1))
        triangles=model.triangles[mask];n=model.face_normals[mask];centers=centers[mask]
        depth=1 if axis==0 else 0
        sign=1 if axis==0 else -1
        scale=min((width-16)/(ur[1]-ur[0]),(height-16)/(zr[1]-zr[0]))
        px=(8+(width-16-(ur[1]-ur[0])*scale)/2+(triangles[:,:,axis]-ur[0])*scale).astype(int)
        py=(height-8-(triangles[:,:,2]-zr[0])*scale).astype(int)
        order=np.argsort(centers[:,depth]*sign)
        light=np.clip(.42+.58*np.abs(n[:,depth]),0,1)
        colors=(light[:,None]*np.array([188,155,107])).astype(np.uint8)
        panel=Image.new('RGB',(width,height),'#f4f2ec');paint=ImageDraw.Draw(panel)
        for i in order:
            paint.polygon([(int(a),int(b)) for a,b in zip(px[i],py[i])],fill=tuple(colors[i]))
        sheet.paste(panel,(x,y));draw=ImageDraw.Draw(sheet)
        draw.text((x,y-25),title,fill='#343b35',font=small)
        draw.rectangle((x,y,x+width,y+height),outline='#c1c1b8')
out=ROOT/'build/preview/anatomy_preservation.jpg'
sheet.save(out,quality=82)
print({'path':str(out),'dimensions':sheet.size,'bytes':out.stat().st_size})
