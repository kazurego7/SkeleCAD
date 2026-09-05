"""R2: C4 spherical fit comparison, independent of production and R1 outputs."""
import json,math
import FreeCAD as App
import Part,MeshPart
import freecad_project as authority
import joint_retention_trial as base

C=authority.PARAMS['joint_holding_trial'];OUT=authority.ROOT/C['output_directory']

def variants(config=None):
    config=C if config is None else config
    return [{**v,**{k:config[k] for k in ('neck_diameter_mm','retention_diameter_mm')}} for v in config['variants']]

def check(socket,variant,config=None):
    config=C if config is None else config
    r=base.CFG['ball_diameter_mm']/2;ball=Part.makeSphere(r)
    stud=ball.fuse(Part.makeCylinder(config['neck_diameter_mm']/2,base.CFG['ball_key_handle_x_mm'],App.Vector(),App.Vector(1,0,0)))
    seated=socket.common(ball).Volume;tol=config['boolean_tolerance_mm3'];sweeps=[]
    # H3 deliberately has 0.025 mm radial interference. Only the spherical
    # overlap is intentional; an extra stem/rim intersection is still a failure.
    for az in range(0,360,config['motion_azimuth_step_deg']):
        a=math.radians(az);axis=App.Vector(0,math.cos(a),math.sin(a));clear=-1;samples=[]
        for angle in range(0,config['motion_limit_deg']+1,config['motion_step_deg']):
            moved=stud.copy();moved.rotate(App.Vector(),axis,angle)
            extra=max(0.,socket.common(moved).Volume-seated)
            samples.append({'angle_deg':angle,'additional_stem_overlap_mm3':extra})
            if extra>tol:break
            clear=angle
        sweeps.append({'azimuth_deg':az,'clear_deg':clear,'samples':samples})
    withdrawal=[socket.common(Part.makeSphere(r,App.Vector(x/10,0,0))).Volume for x in range(0,51,2)]
    capture=max(withdrawal)-seated
    if variant['cavity_clearance_mm']>=0 and seated>tol:raise ValueError('Unexpected seated interference')
    if variant['cavity_clearance_mm']<0 and seated<=tol:raise ValueError('Missing intended spherical preload geometry')
    if capture<=tol:raise ValueError('No additional geometric withdrawal barrier')
    if min(s['clear_deg'] for s in sweeps)<config['required_motion_deg']:raise ValueError('Insufficient stem motion clearance')
    return {'name':variant['label'],'passed':True,'neck_diameter_mm':config['neck_diameter_mm'],
            'cavity_diameter_mm':2*r+variant['cavity_clearance_mm'],'radial_clearance_mm':variant['cavity_clearance_mm']/2,
            'intentional_spherical_overlap_mm3':seated,'additional_withdrawal_barrier_mm3':capture,
            'motion':sweeps,'physical_holding_torque_verified':False}

def generate(config_key='joint_holding_trial',document_name='HoldingTrialR2'):
    config=authority.PARAMS[config_key];out=authority.ROOT/config['output_directory']
    (out/'parts').mkdir(parents=True,exist_ok=True)
    doc=App.newDocument(document_name);records=[];audits=[];assembly=[]
    for i,var in enumerate(variants(config)):
        socket=base.deep_c4(var);ball=base.ball_key(config['neck_diameter_mm'],var['label_dots'])
        for suffix,shape in (('socket',socket),('ball_key',ball)):
            name=var['label']+'_'+suffix
            if not shape.isValid() or len(shape.Solids)!=1 or shape.Volume<=0:raise ValueError(name+' invalid CAD')
            obj=doc.addObject('PartDesign::Feature',name);obj.Shape=shape
            shape.exportStep(str(out/'parts'/(name+'.step')))
            mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=base.CFG['mesh_linear_deflection_mm'],AngularDeflection=base.CFG['mesh_angular_deflection_rad'],Relative=False)
            if not mesh.isSolid():raise ValueError(name+' open mesh')
            for ext in ('stl','3mf'):mesh.write(str(out/'parts'/(name+'.'+ext)))
            records.append({'name':name,'cad_valid':True,'solids':1,'volume_mm3':shape.Volume,'triangles':mesh.CountFacets})
            assembly.append(base.shifted(shape,(0,i*config['preview_spacing_mm'],0)))
        audit=check(socket,var,config);audits.append(audit)
        print(json.dumps({k:v for k,v in audit.items() if k!='motion'}),flush=True)
    doc.recompute();doc.saveAs(str(out/(document_name+'.FCStd')))
    mesh=MeshPart.meshFromShape(Shape=Part.makeCompound(assembly),LinearDeflection=base.CFG['mesh_linear_deflection_mm'],AngularDeflection=base.CFG['mesh_angular_deflection_rad'],Relative=False)
    mesh.write(str(out/'assembly.stl'))
    (out/'cad_report.json').write_text(json.dumps({'trial':config['revision'],'parts':records,'production_geometry_changed':False},indent=2),encoding='utf-8')
    (out/'mechanical_audit.json').write_text(json.dumps({'passed':True,'variants':audits,'parameters':config,
        'physical_retention_verified':False,'scope':'Rigid mouth/stem sweep with intentional spherical interference reported separately. No elastic deformation, holding torque, insertion force, plasticity or fatigue prediction.'},indent=2),encoding='utf-8')

if __name__=='__main__':generate()
