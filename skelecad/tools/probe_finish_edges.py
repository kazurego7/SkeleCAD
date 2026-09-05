"""Inspect exact cup symmetry and inner/slot edge finishing without production writes."""
import sys, json, math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import FreeCAD as App
import Part
import trex_v2_project as p

outer,cut=p.socket_local(); shell=outer.cut(cut).removeSplitter()
for normal in (App.Vector(0,1,0),App.Vector(0,0,1)):
    mirrored=shell.mirror(App.Vector(),normal)
    print('MIRROR',str(normal),'difference',shell.cut(mirrored).Volume,flush=True)
for i,e in enumerate(shell.Edges):
    b=e.BoundBox
    print('EDGE',i,round(e.Length,4),[round(x,4) for x in (b.XMin,b.XMax,b.YMin,b.YMax,b.ZMin,b.ZMax)],flush=True)
mouth=[e for e in shell.Edges if abs(e.BoundBox.XMin-1.5)<1e-6 and abs(e.BoundBox.XMax-1.5)<1e-6 and e.Length>5]
for radius in (1.0,0.5,0.2):
    try:
        shape=shell.makeFillet(radius,mouth)
        ball=Part.makeSphere(3)
        barrier=max(shape.common(Part.makeSphere(3,App.Vector(x/10,0,0))).Volume for x in range(1,31))
        print('FILLET',radius,'valid',shape.isValid(),'solids',len(shape.Solids),'seated',shape.common(ball).Volume,'barrier',barrier,flush=True)
    except Exception as exc:print('FILLET FAILED',radius,str(exc),flush=True)
