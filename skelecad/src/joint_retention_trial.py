"""All-printed calibration experiment; deliberately does NOT replace production joints.

The two socket halves are placed around the ball. Two double-dovetail keys
slide from the mouth end along +/-Y rails. Their shallow longitudinal taper
draws the halves together without pushing a ball through an undersized lip.
Friction, print tolerances and long-term wedge retention need physical testing.
"""
import json, math
from pathlib import Path
import FreeCAD as App
import Part, MeshPart
import freecad_project as authority

CFG = authority.PARAMS['joint_retention_trial']
OUT = authority.ROOT / CFG['output_directory']
V = App.Vector

def shifted(shape, xyz):
    out=shape.copy();out.translate(V(*xyz));return out

def profile(x, yc, height, waist):
    slope=CFG['dovetail_slope'];wide=waist+slope*height
    yz=[(-waist,0),(-wide,height),(wide,height),(waist,0),
        (wide,-height),(-wide,-height),(-waist,0)]
    return Part.makePolygon([V(x,yc+y,z) for y,z in yz])

def tapered_rail(x0,x1,yc,height,clearance=0):
    def wire(x):return profile(x,yc,height,CFG['groove_waist_mm']+CFG['taper_slope']*x-clearance)
    return Part.makeLoft([wire(x0),wire(x1)],True,True)

def cup(clearance):
    ri=(CFG['ball_diameter_mm']+clearance)/2;ro=CFG['outer_radius_mm']
    h=CFG['front_height_mm'];r=CFG['rim_radius_mm'];cx=h-r
    cy=math.sqrt((ro-r)**2-cx*cx);a=math.atan2(cx,cy)
    p=lambda radius,t:V(radius*math.sin(t),radius*math.cos(t),0)
    rear=V(-ro,0,0);join=p(ro,a);front=V(h,cy,0);c=V(cx,cy,0)
    mid=c+V(r*math.cos((math.pi/2-a)/2),r*math.sin((math.pi/2-a)/2),0)
    edges=[Part.Arc(rear,p(ro,(a-math.pi/2)/2),join).toShape(),
           Part.Arc(join,mid,front).toShape(),Part.makeLine(front,V(h,0,0)),Part.makeLine(V(h,0,0),rear)]
    outside=Part.Face(Part.Wire(edges)).revolve(V(),V(1,0,0),360)
    angle=math.radians(CFG['mouth_relief_deg']);n=CFG['neck_diameter_mm']/2/math.cos(angle)
    cone=Part.makeCone(n,n+2*ro*math.tan(angle),2*ro,V(),V(1,0,0))
    cut=Part.makeSphere(ri).fuse(cone)
    return outside,cut

def socket_halves(clearance,number):
    outside,cut=cup(clearance)
    back=CFG['rail_rear_x_mm'];front=CFG['rail_front_x_mm'];edge=CFG['rail_outer_y_mm']
    height=CFG['rail_height_mm'];yc=CFG['rail_center_y_mm']
    # Solid side rails, open at their two ends; no flexible snap tongues.
    for sign in (-1,1):
        block=Part.makeBox(front-back,edge-(yc-2.5),2*height,V(back, yc-2.5 if sign>0 else -edge,-height))
        block=block.makeFillet(CFG['rim_radius_mm'],block.Edges)
        outside=outside.fuse(block)
    shell=outside.cut(cut)
    for sign in (-1,1):
        shell=shell.cut(tapered_rail(back-1,front+1,sign*yc,CFG['groove_half_height_mm']))
    gap=CFG['parting_gap_mm']
    top=shell.common(Part.makeBox(40,40,20,V(-20,-20,gap/2))).removeSplitter()
    bottom=shell.common(Part.makeBox(40,40,20,V(-20,-20,-20-gap/2))).removeSplitter()
    # Matching one/two/three tactile dimples on outer rail faces.
    for index in range(number):
        x=back+1.8+2.1*index
        for sign in (-1,1):
            dot=Part.makeSphere(CFG['label_dot_radius_mm'],V(x,sign*(edge+CFG['label_dot_radius_mm']-CFG['label_dot_depth_mm']),3.0))
            top=top.cut(dot)
            dot=Part.makeSphere(CFG['label_dot_radius_mm'],V(x,sign*(edge+CFG['label_dot_radius_mm']-CFG['label_dot_depth_mm']),-3.0))
            bottom=bottom.cut(dot)
    return bottom.removeSplitter(),top.removeSplitter()

def key():
    from trex_v2_project import capsule
    x0=CFG['key_rear_x_mm'];x1=CFG['key_front_x_mm'];h=CFG['key_half_height_mm']
    shape=tapered_rail(x0,x1,0,h,CFG['key_side_clearance_mm'])
    # Transverse pull handle also stops over-insertion before the cavity crushes.
    handle_r=CFG['handle_height_mm']/2
    handle_x=x1+CFG['handle_length_mm']/2
    handle_y=CFG['handle_width_mm']/2-handle_r
    handle=capsule((handle_x,-handle_y,0),(handle_x,handle_y,0),handle_r)
    return shape.fuse(handle).removeSplitter()

def ball_key(neck_diameter=None,label_dots=None):
    from trex_v2_project import capsule
    r=CFG['ball_diameter_mm']/2;end=CFG['ball_key_handle_x_mm'];half=CFG['ball_key_handle_length_mm']/2
    neck=CFG['neck_diameter_mm'] if neck_diameter is None else neck_diameter
    result=Part.makeSphere(r).fuse(Part.makeCylinder(neck/2,end,V(),V(1,0,0))).fuse(
        capsule((end,-half,0),(end,half,0),CFG['ball_key_handle_radius_mm'])).removeSplitter()
    number=label_dots if label_dots is not None else (3 if neck_diameter is None else 1+next(i for i,v in enumerate(CFG['deep_c4']['variants']) if v['neck_diameter_mm']==neck))
    for i in range(number):
        dot=Part.makeSphere(CFG['label_dot_radius_mm'],V(end+CFG['ball_key_handle_radius_mm']+CFG['label_dot_radius_mm']-CFG['label_dot_depth_mm'],(i-(number-1)/2)*2.4,0))
        result=result.cut(dot)
    return result.removeSplitter()

def deep_c4(variant, return_void=False, include_mount=True, include_labels=True):
    cfg=CFG['deep_c4'];ri=(CFG['ball_diameter_mm']+variant.get('cavity_clearance_mm',cfg['cavity_clearance_mm']))/2
    edge=cfg['wall_mm']/2;ro=ri+cfg['wall_mm'];mid=ri+edge
    radial=variant['retention_diameter_mm']/2+edge;a=math.acos(radial/mid)
    p=lambda r,t:V(r*math.sin(t),r*math.cos(t),0)
    rear=V(-ro,0,0);back=V(-ri,0,0);c=p(mid,a);front=c+V(edge,0,0)
    outer_join=p(ro,a);inner_join=p(ri,a)
    arc_mid=c+V(edge*math.cos((math.pi/2-a)/2),edge*math.sin((math.pi/2-a)/2),0)
    oe=[Part.Arc(rear,p(ro,(a-math.pi/2)/2),outer_join).toShape(),
        Part.Arc(outer_join,arc_mid,front).toShape(),Part.makeLine(front,V(front.x,0,0)),Part.makeLine(V(front.x,0,0),rear)]
    ie=[Part.Arc(back,p(ri,(a-math.pi/2)/2),inner_join).toShape(),
        Part.Arc(inner_join,c+V(0,-edge,0),front).toShape(),
        Part.makeLine(front,V(ro+2,ro+2,0)),Part.makeLine(V(ro+2,ro+2,0),V(ro+2,0,0)),Part.makeLine(V(ro+2,0,0),back)]
    outer=Part.Face(Part.Wire(oe)).revolve(V(),V(1,0,0),360)
    cut=Part.Face(Part.Wire(ie)).revolve(V(),V(1,0,0),360)
    slot=cfg['slot_width_mm'];sx=cfg['slot_root_x_mm']+slot/2
    # Two perpendicular through-slots create four petals. Semicircular closed
    # ends avoid the former square, very short flexure roots.
    slit=Part.makeBox(2*ro-sx,slot,2*ro+2,V(sx,-slot/2,-ro-1)).fuse(
        Part.makeCylinder(slot/2,2*ro+2,V(sx,0,-ro-1),V(0,0,1)))
    cross=slit.copy();cross.rotate(V(),V(1,0,0),90)
    shell=outer.cut(cut.fuse(slit).fuse(cross)).removeSplitter()
    result=shell
    if include_mount:
        mount=Part.makeCylinder(cfg['mount_radius_mm'],cfg['mount_length_mm'],V(-ro-cfg['mount_length_mm']+1,0,0),V(1,0,0))
        result=result.fuse(mount)
    if include_labels:
        if not include_mount:raise ValueError('Labels require the calibration mount')
        number=variant['label_dots'] if 'label_dots' in variant else 1+next(i for i,v in enumerate(cfg['variants']) if v['label']==variant['label'])
        for i in range(number):
            dot=Part.makeSphere(CFG['label_dot_radius_mm'],V(-ro-cfg['mount_length_mm']+1-CFG['label_dot_radius_mm']+CFG['label_dot_depth_mm'],(i-(number-1)/2)*2.4,0))
            result=result.cut(dot)
    result=result.removeSplitter()
    return (result,cut.fuse(slit).fuse(cross)) if return_void else result

def export(name,shape,doc):
    assert shape.isValid() and len(shape.Solids)==1,(name,'invalid or disconnected')
    obj=doc.addObject('PartDesign::Feature',name);obj.Shape=shape
    shape.exportStep(str(OUT/'parts'/f'{name}.step'))
    mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=CFG['mesh_linear_deflection_mm'],
          AngularDeflection=CFG['mesh_angular_deflection_rad'],Relative=False)
    mesh.write(str(OUT/'parts'/f'{name}.stl'))
    mesh.write(str(OUT/'parts'/f'{name}.3mf'))
    return {'name':name,'cad_valid':True,'solids':1,'volume_mm3':shape.Volume,'triangles':mesh.CountFacets}

def generate():
    (OUT/'parts').mkdir(parents=True,exist_ok=True)
    doc=App.newDocument('RetentionTrialR1');rows=[];variants=[]
    for num,clearance in enumerate(CFG['cavity_clearances_mm'],1):
        lower,upper=socket_halves(clearance,num)
        rows += [export(f'socket_{num}_lower',lower,doc),export(f'socket_{num}_upper',upper,doc)]
        variants.append({'number':num,'cavity_diameter_mm':CFG['ball_diameter_mm']+clearance,'clearance_mm':clearance})
    rows += [export('locking_key',key(),doc),export('ball_key',ball_key(),doc)]
    for variant in CFG['deep_c4']['variants']:
        label=variant['label']
        rows += [export(label+'_socket',deep_c4(variant),doc),export(label+'_ball_key',ball_key(variant['neck_diameter_mm']),doc)]
    doc.recompute();doc.saveAs(str(OUT/'RetentionTrialR1.FCStd'))
    lower,upper=socket_halves(CFG['cavity_clearances_mm'][1],2)
    assembled=[lower,upper,ball_key()]+[shifted(key(),(0,s*CFG['rail_center_y_mm'],0)) for s in (-1,1)]
    assembly=Part.makeCompound(assembled)
    mesh=MeshPart.meshFromShape(Shape=assembly,LinearDeflection=0.025,AngularDeflection=0.1,Relative=False)
    mesh.write(str(OUT/'assembly.stl'))
    report={'trial':CFG['revision'],'production_geometry_changed':False,'variants':variants,'parts':rows,
            'physical_retention_verified':False,'assembly_method':'Place halves around ball, insert two tapered keys from front, tighten alternately without force.',
            'scope':'All printed PLA; no external hardware. Requires calibration before any production integration.'}
    (OUT/'cad_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':generate()
