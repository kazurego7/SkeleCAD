"""Compare rotationally symmetric lip relief without editing production geometry."""
import sys, math, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import FreeCAD as App
import Part
import trex_v2_project as p
from validate_joint_v2 import inserted_stud,axis_sweep
p.JOINT['socket_profile'].pop('circumferential_relief',None)
outer,cut=p.socket_local();baseline=outer.cut(cut).removeSplitter()
for angle in (27.5,30,32.5,35,40):
    length=p.JOINT['socket_outer_diameter_mm']
    r=p.JOINT['neck_diameter_mm']/2/math.cos(math.radians(angle))
    cone=Part.makeCone(r,r+length*math.tan(math.radians(angle)),length,App.Vector(),App.Vector(1,0,0))
    shell=baseline.cut(cone).removeSplitter()
    barriers=[]
    for x in [i/20 for i in range(1,81)]:
        barriers.append(shell.common(Part.makeSphere(p.JOINT['ball_diameter_mm']/2,App.Vector(x,0,0))).Volume)
    maximum=max(barriers)
    peak=(barriers.index(maximum)+1)/20
    row={'angle':angle,'valid':shell.isValid(),'solids':len(shell.Solids),
         'removed_mm3':baseline.Volume-shell.Volume,'barrier_max_mm3':maximum,'barrier_x':peak,
         'motion_deg':axis_sweep(shell,inserted_stud(),(0,1,0))[0]}
    print(json.dumps(row),flush=True)
