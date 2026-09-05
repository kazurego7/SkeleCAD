"""Read-only height-trim experiment; no source geometry is edited."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import FreeCAD as App
import Part
import trex_v2_project as p
from validate_joint_v2 import inserted_stud,axis_sweep
p.JOINT['socket_profile'].pop('height_trim',None)
outer,cut=p.socket_local();baseline=outer.cut(cut).removeSplitter()
for height in (1.4,1.5,1.6,1.8):
    shell=baseline.cut(Part.makeBox(10,20,20,App.Vector(height,-10,-10))).removeSplitter()
    # Round only the outer circular edge at the new mouth; inner aperture must
    # not be silently enlarged or squeeze the nominally seated ball.
    candidates=[e for e in shell.Edges if abs(e.BoundBox.XMin-height)<1e-6 and abs(e.BoundBox.XMax-height)<1e-6 and e.Length>10]
    for fillet in (False,True):
        test=shell
        if fillet:
            try:test=shell.makeFillet(1.,[max(candidates,key=lambda e:e.Length)])
            except Exception as error:
                print({'height':height,'fillet_failed':str(error)},flush=True);continue
        overlaps=[test.common(Part.makeSphere(3,App.Vector(x/20,0,0))).Volume for x in range(1,61)]
        print(json.dumps({'height':height,'fillet':fillet,'valid':test.isValid(),'solids':len(test.Solids),
            'volume':test.Volume,'removed':baseline.Volume-test.Volume,'barrier_max':max(overlaps),
            'seated':test.common(Part.makeSphere(3)).Volume,
            'pitch':axis_sweep(test,inserted_stud(),(0,1,0))[0],'yaw':axis_sweep(test,inserted_stud(),(0,0,1))[0]}),flush=True)
