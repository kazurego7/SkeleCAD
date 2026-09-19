"""Exact tools for image jobs. Enter through freecad_project.py, not a GUI.

The C4 family remains experimental, and is never written to production outputs.
Requests contain local coordinates, not code, executable names or output paths.
"""
import json
import shutil
from pathlib import Path
import FreeCAD as App
import Part
import MeshPart
import Mesh
import freecad_project as authority
from trex_v2_project import capsule
from joint_retention_trial import deep_c4
from workflow_cad_cache import cache_key,read_entry,save_entry,digest

V=App.Vector


def safe_refine(shape):
    """Remove splitter faces only when OpenCascade keeps a valid solid.

    Some oblique socket/bridge intersections are valid before refinement but
    become invalid after removeSplitter().  Refinement is cosmetic and must
    never replace the valid Boolean result with broken topology.
    """
    refined=shape.removeSplitter()
    if refined.isValid() and refined.Solids and refined.Volume>0:return refined,False
    if shape.isValid() and shape.Solids and shape.Volume>0:return shape,True
    return refined,False


def workflow_socket_shell(variant):
    """Return the rounded C4 shell used on an anatomy attachment.

    The cylindrical mount and label dimples belong only to the standalone
    retention calibration coupons.  Workflow sockets already receive a
    capsule bridge to anatomy, so carrying the coupon mount into the model
    creates an unnecessary flat boss on the back of the socket.
    """
    return deep_c4(variant,return_void=True,include_mount=False,include_labels=False)


def socket_rotation(axis, symmetry_axis='x'):
    """Fix roll using the symmetry plane, not a shortest-arc rotation.

    C4 cuts are invariant under local Y/Z reflection. Projecting the plane
    normal into the cross-section therefore mirrors paired slots and gives
    centre-plane sockets a reflection-symmetric slot plane.
    """
    axis=V(axis);axis.normalize()
    normal={'x':V(1,0,0),'y':V(0,1,0),'z':V(0,0,1)}[symmetry_axis]
    transverse=normal-axis*normal.dot(axis)
    if transverse.Length<1e-8:
        # Axes normal to the symmetry plane have no preferred projected normal.
        reference=V(0,0,1) if symmetry_axis!='z' else V(0,1,0)
        transverse=reference-axis*reference.dot(axis)
    transverse.normalize()
    return App.Rotation(axis,transverse,axis.cross(transverse),'XYZ')


def resolve_workflow_variant(cfg,params):
    trial=params['joint_retention_trial']
    variant=dict(next(v for v in trial['deep_c4']['variants'] if v['label']==cfg['joint_variant']))
    clearance=cfg.get('cavity_clearance_mm',trial['deep_c4']['cavity_clearance_mm'])
    selection=cfg.get('fit_selection')
    if selection:
        source=params[selection['source_trial']]
        selected=next(v for v in source['variants'] if v['label']==selection['source_variant'])
        if selection.get('physical_fit_result')!='user_selected' or clearance!=selected['cavity_clearance_mm']:
            raise ValueError('Workflow clearance does not match the physically selected fit')
        for key in ('neck_diameter_mm','retention_diameter_mm'):
            if variant[key]!=source[key]:raise ValueError('Selected fit uses different joint geometry')
    elif not 0 <= clearance <= trial['deep_c4']['cavity_clearance_mm']:
        raise ValueError('Interference fit requires a physically selected calibration variant')
    variant['cavity_clearance_mm']=clearance
    return variant


def generate(request_path):
    request_path=Path(request_path).resolve()
    request=json.loads(request_path.read_text(encoding='utf-8'))
    cfg=request['settings']['manufacturing']
    trial=authority.PARAMS['joint_retention_trial']
    if cfg['joint_family']!='retention_trial_deep_c4':raise ValueError('Unsupported joint family')
    variant=resolve_workflow_variant(cfg,authority.PARAMS)
    if request['trial_parameters']!=trial:raise ValueError('Joint settings changed; regenerate the request')
    out=request_path.parent/'tools';out.mkdir(exist_ok=True)
    doc=App.newDocument('ImageWorkflowTools');reports=[];refinement_fallbacks=[]
    project=Path(__file__).resolve().parents[1]
    cache_root=project/'.runtime'/'workflow-cad-cache'
    context={'sources':{p.name:digest(p) for p in sorted((project/'src').glob('*.py'))},
             'parameters':authority.PARAMS,'settings':request['settings'],
             'toolchain':digest(project/'config/toolchain.json'),'freecad':list(App.Version())}
    hits=0

    def export(name,shape):
        if not shape.isValid() or not shape.Solids or shape.Volume<=0:raise ValueError(f'Invalid CAD {name}')
        obj=doc.addObject('PartDesign::Feature',name);obj.Shape=shape
        shape.exportStep(str(out/(name+'.step')))
        shape.exportBrep(str(out/(name+'.brep')))
        mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=trial['mesh_linear_deflection_mm'],
                                   AngularDeflection=trial['mesh_angular_deflection_rad'],Relative=False)
        mesh.write(str(out/(name+'.stl')))
        reports.append({'name':name,'valid':True,'solids':len(shape.Solids),'volume_mm3':shape.Volume})

    # All joints in this request use exactly the same local C4 shape. Build its
    # Boolean geometry once, then make independent copies before placement.
    templates=None
    for joint in request['joints']:
        name=joint['name'];center=V(*joint['center'])
        # A finite spherical excision removes only the inferred old joint bulb.
        if request['phase']=='cut':
            export(name+'_cut',Part.makeSphere(joint['cut_radius_mm'],center))
            continue
        key=cache_key(context,joint);cached=read_entry(cache_root,key)
        if cached:
            directory,entry=cached
            expected={name+'_'+kind for kind in ('shell','socket','void','cavity','ball')}
            if {p['name'] for p in entry['parts']}!=expected:raise ValueError('CAD cache part mismatch')
            if set(entry['files'])!={n+ext for n in expected for ext in ('.brep','.step','.stl')}:
                raise ValueError('CAD cache file set mismatch')
            for record in entry['parts']:
                shape=Part.Shape();shape.read(str(directory/(record['name']+'.brep')))
                if not shape.isValid() or not shape.Solids or shape.Volume<=0:
                    raise ValueError('Cached CAD is invalid')
                obj=doc.addObject('PartDesign::Feature',record['name']);obj.Shape=shape
            for filename in entry['files']:shutil.copy2(directory/filename,out/filename)
            reports.extend(entry['parts']);refinement_fallbacks.extend(entry['fallbacks']);hits+=1
            continue
        before=len(reports);fallback_before=len(refinement_fallbacks)
        if templates is None:templates=workflow_socket_shell(variant)
        axis=V(*joint.get('tool_direction',joint['direction']));axis.normalize()
        symmetry_axis=authority.PARAMS['image_workflow']['partition_review']['symmetry_mirroring'].get('axis','x')
        placement=App.Placement(center,socket_rotation(axis,symmetry_axis))
        shell,void=(shape.copy() for shape in templates)
        shell.Placement=placement;shell=shell.copy()
        void.Placement=placement;void=void.copy()
        ri=(trial['ball_diameter_mm']+variant['cavity_clearance_mm'])/2
        ro=ri+trial['deep_c4']['wall_mm']
        cavity=Part.makeSphere(ri,center)
        back=center-axis*(ro-cfg['socket_bridge_overlap_mm'])
        bridge=capsule(tuple(back),tuple(joint.get('socket_anchor',joint['parent_anchor'])),cfg['socket_bridge_radius_mm'])
        # Cut the bridge first, then unite it with the already hollow shell.
        # This is the same final volume, but avoids an OpenCascade edge case in
        # (shell + bridge) - void that can triangulate with an open micro-seam.
        socket,fallback=safe_refine(shell.fuse(bridge.cut(void)))
        if fallback:refinement_fallbacks.append(name+'_socket')
        ball,fallback=safe_refine(Part.makeSphere(trial['ball_diameter_mm']/2,center).fuse(
            capsule(tuple(center),tuple(joint.get('ball_anchor',joint['child_anchor'])),variant['neck_diameter_mm']/2)))
        if fallback:refinement_fallbacks.append(name+'_ball')
        export(name+'_shell',shell)
        export(name+'_socket',socket);export(name+'_void',void);export(name+'_cavity',cavity);export(name+'_ball',ball)
        records=reports[before:]
        save_entry(cache_root,key,out,[r['name']+ext for r in records for ext in ('.brep','.step','.stl')],
                   records,refinement_fallbacks[fallback_before:])
    doc.recompute();doc.saveAs(str(out/'JointTools.FCStd'))
    report={'phase':request['phase'],'parts':reports,'refinement_fallbacks':refinement_fallbacks,'physical_fit_verified':False,
            'cached_joints':hits,
            'socket_slit_orientation':'symmetry_plane_projected_frame_v1',
            'joint_family':cfg['joint_family'],'joint_variant':variant['label'],
            'cavity_clearance_mm':variant['cavity_clearance_mm'],
            'fit_selection':cfg.get('fit_selection'),
            'workflow_socket_back':'rounded_shell_without_calibration_mount_or_label_dimples'}
    (out/('cad_'+request['phase']+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


def assembly_document(directory):
    """Mesh anatomy in FCStd, with exact joint STEP tools kept separately.

    Do not claim image-derived anatomy is a parametrically editable CAD solid.
    """
    directory=Path(directory).resolve();manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    doc=App.newDocument('ImageModelAssembly');meshes=[]
    for part in manifest['parts']:
        mesh=Mesh.Mesh(str(directory/part['filename']))
        if not mesh.isSolid():raise ValueError('Not a solid mesh: '+part['name'])
        obj=doc.addObject('Mesh::Feature',part['name']);obj.Label=part['label'];obj.Mesh=mesh
        mesh.write(str(directory/(part['name']+'.3mf')));meshes.append(mesh)
    compound=Mesh.Mesh()
    for mesh in meshes:compound.addMesh(mesh)
    compound.write(str(directory/'assembly.stl'))
    doc.recompute();doc.saveAs(str(directory/'Assembly.FCStd'))
    return len(meshes)
