"""Read-only CAD comparison of the old socket and rounded shallow profiles."""
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import FreeCAD as App
import Part
import trex_v2_project as project
import validate_joint_v2 as validation

def rounded_socket(angle):
    ri=project.JOINT['socket_diameter_mm']/2
    ro=project.JOINT['socket_outer_diameter_mm']/2
    mid=(ro+ri)/2;edge=(ro-ri)/2;a=math.radians(angle)
    def p(r,t):return App.Vector(r*math.sin(t),r*math.cos(t),0)
    rear=App.Vector(-ro,0,0);back=App.Vector(-ri,0,0)
    c=p(mid,a);front=c+App.Vector(edge,0,0)
    edges=[Part.Arc(rear,p(ro,(a-math.pi/2)/2),p(ro,a)).toShape(),
           Part.Arc(p(ro,a),front,p(ri,a)).toShape(),
           Part.Arc(p(ri,a),p(ri,(a-math.pi/2)/2),back).toShape(),Part.makeLine(back,rear)]
    return Part.Face(Part.Wire(edges)).revolve(App.Vector(),App.Vector(1,0,0),360)

if __name__=='__main__':
    old=validation.socket();stud=validation.inserted_stud()
    for angle in [None,20,22,24,26,28]:
        s=old if angle is None else rounded_socket(angle)
        print('PROFILE',angle,'valid',s.isValid(),'solids',len(s.Solids),'front',s.BoundBox.XMax,'volume',s.Volume,flush=True)
        for axis in [(0,1,0),(0,0,1)]:
            clear,samples=validation.axis_sweep(s,stud,axis)
            print('sweep',axis,clear,[(v['angle_deg'],round(v['overlap_volume_mm3'],5))for v in samples],flush=True)
        ball=Part.makeSphere(project.JOINT['ball_diameter_mm']/2)
        ball.translate(App.Vector(1,0,0))
        print('ball_pull_1mm_overlap',s.common(ball).Volume,flush=True)
