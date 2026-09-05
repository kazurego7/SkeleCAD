"""Diagnostic section plots of existing meshes; does not alter geometry."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import trimesh
ROOT=Path(__file__).resolve().parents[1]
H=ROOT/'build/hybrid_20260830'
image=Image.new('RGB',(1200,950),'white');draw=ImageDraw.Draw(image)
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
for col,(zone,xlim,zlim) in enumerate([('neck',(-76,-44),(68,98)),('tail root',(-8,22),(40,74))]):
    for row,folder in enumerate(['raw_split','parts']):
        ox=col*600+55;oy=row*475+40;scale=12
        def coord(x,z):return (ox+(x-xlim[0])*scale,oy+(zlim[1]-z)*scale)
        for x in range(xlim[0],xlim[1]+1,4):
            a,b=coord(x,zlim[0]),coord(x,zlim[1]);draw.line([a,b],fill='#dddddd');draw.text(a,str(x),fill='black',font=font)
        for z in range(zlim[0],zlim[1]+1,4):
            a,b=coord(xlim[0],z),coord(xlim[1],z);draw.line([a,b],fill='#dddddd');draw.text((a[0]-30,a[1]),str(z),fill='black',font=font)
        for name,color in [('torso','#777777'),('head','#bd851f'),('tail','#c57332')]:
            mesh=trimesh.load_mesh(H/folder/f'{name}.stl')
            section=mesh.section(plane_origin=[0,0,0],plane_normal=[0,1,0])
            if section:
                for line in section.discrete:
                    for a,b in zip(line[:-1],line[1:]):
                        if all(xlim[0]<=p[0]<=xlim[1] and zlim[0]<=p[2]<=zlim[1] for p in (a,b)):
                            draw.line([coord(a[0],a[2]),coord(b[0],b[2])],fill=color,width=2)
        draw.text((ox,oy-25),f'{zone}: {folder} / Y=0',fill='black',font=font)
image.save(ROOT/'.runtime/neck_tail_sections.png')
