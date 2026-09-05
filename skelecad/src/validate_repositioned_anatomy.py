"""Check the source-to-partition-to-repositioned-solid chain without erasure.

Rigid translations are inverted for the source comparison. For final parts,
only the actual enabled machining tools and independently bounded cut-edge
finishing tools may remove material, never a broad joint-radius exemption.
Moved arms retain their raw volume except for the authorized border finishing.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from hybrid_context import H, HYBRID, INPUT, PARAMS

ROOT=Path(__file__).resolve().parents[1]
OWNERS={'neck':('head','torso'),'shoulder_left':('arm_left','torso'),
        'shoulder_right':('arm_right','torso'),'hip_left':('leg_left','torso'),
        'hip_right':('leg_right','torso'),'tail_root':('tail','torso'),
        'ankle_left':('foot_left','leg_left'),'ankle_right':('foot_right','leg_right')}


def outside_disc(points,center,axis,radius,thickness):
    axis=np.asarray(axis,dtype=float);axis/=np.linalg.norm(axis)
    relative=points-np.asarray(center)
    axial=relative@axis
    radial=np.linalg.norm(relative-axial[:,None]*axis,axis=1)
    tol=H['preservation_tolerance_mm']
    return (np.abs(axial)>thickness/2+tol)|(radial>radius+tol)


def partition_protected(points):
    keep=np.ones(len(points),dtype=bool)
    for spec in H['connections']:
        name=spec['name'];axis=np.array(spec['mouth_direction'],dtype=float)
        center=np.array(H['partition_centers_mm'][name])+axis*H['local_cut_offsets_mm'].get(name,0)
        keep &= outside_disc(points,center,axis,H['local_cut_radii_mm'][name],H['part_gap_mm'])
    spec=H['hip_ring_transfer']
    for sign in [1,-1]:
        center=np.array(spec['seam_center_left_mm']);center[1]*=sign
        keep &= outside_disc(points,center,spec['seam_normal'],spec['seam_radius_mm'],spec['seam_gap_mm'])
    return keep


def volume(mesh):
    return abs(float(mesh.volume)) if len(mesh.faces) else 0.0


def load_tool(name):
    if name.endswith('_edge_finish'):
        arrays=np.load(HYBRID/'joint_tools'/f'{name}.npz')
        mesh=trimesh.Trimesh(arrays['vertices'],arrays['faces'],process=False)
        if not mesh.is_volume:raise RuntimeError(f'Invalid finishing tool: {name}')
        return mesh
    return trimesh.load_mesh(HYBRID/'joint_tools'/f'{name}.stl')


def exact_boolean(meshes,operation):
    # Keep internal finish allowance faces in float64; STL precision is only
    # appropriate for final printable parts, not tiny diagnostic differences.
    from finish_cut_edges import solid
    result=solid(meshes[0])
    for mesh in meshes[1:]:
        other=solid(mesh)
        result=result-other if operation=='difference' else (result+other if operation=='union' else result^other)
    data=result.to_mesh64()
    return trimesh.Trimesh(data.vert_properties[:,:3],data.tri_verts,process=False)


def validate(report_path):
    raw={p.stem:trimesh.load_mesh(p) for p in sorted((HYBRID/'raw_split').glob('*.stl'))}
    finished={name:trimesh.load_mesh(HYBRID/'parts'/f'{name}.stl') for name in raw}
    unposed=[]
    for name,mesh in raw.items():
        mesh=mesh.copy();mesh.apply_translation(-np.array(H.get('part_translation_mm',{}).get(name,[0,0,0])))
        unposed.append(mesh)
    source=trimesh.load_mesh(INPUT)
    points=source.vertices[partition_protected(source.vertices)]
    distances=cKDTree(np.vstack([m.vertices for m in unposed])).query(points)[0]
    missing=distances>H['preservation_tolerance_mm']
    # The inward ring lap can bury a source surface without deleting material.
    for mesh in unposed:
        candidates=np.flatnonzero(missing & ((points>=mesh.bounds[0])&(points<=mesh.bounds[1])).all(axis=1))
        for start in range(0,len(candidates),64):
            ids=candidates[start:start+64]
            missing[ids[mesh.contains(points[ids])]]=False
    overall={'protected_vertices':len(points),'missing_vertices':int(missing.sum()),
             'passed':not missing.any()}
    allowed={name:[] for name in raw}
    for connection,(male,female) in OWNERS.items():
        allowed[female].append(connection+('_socket_anatomy_cut' if PARAMS['joint'].get('socket_profile') else '_socket_cut'))
        if connection not in H['preserve_anatomy_connections']:
            allowed[male].append(connection+'_source_clear')
            if connection not in H.get('preserve_target_anatomy_connections',[]):
                allowed[female].append(connection+'_target_clear')
    results={}
    for spec in H.get('local_reliefs',[]):
        allowed[spec['part']].append(spec['name'])
    finishing={}
    if H.get('cut_edge_finish'):
        from hybrid_apply_joints import boundary_tools,machining_tools
        from finish_cut_edges import cut_seams,certify_band
        cfg=H['cut_edge_finish'];tool_map=machining_tools()
        for name in raw:
            path=HYBRID/'joint_tools'/f'{name}_edge_finish.npz'
            if not path.exists():continue
            before=trimesh.load_mesh(HYBRID/'edge_finish'/f'{name}_before.stl')
            seeds=np.load(HYBRID/'edge_finish'/f'{name}_seams.npy')
            actual=cut_seams(before,boundary_tools(name,tool_map[name]),cfg)
            seed_error=cKDTree(actual.mean(axis=1)).query(seeds.mean(axis=1))[0].max()
            if seed_error>cfg['tool_surface_tolerance_mm']:
                raise RuntimeError(f'{name}: finish seeds do not belong to actual cut borders')
            cutter=load_tool(name+'_edge_finish')
            bound=certify_band(cutter,seeds,cfg)
            finishing[name]={'seam_edges':len(seeds),'seed_error_mm':float(seed_error),
                             'certified_cutter_band_mm':bound,'passed':True}
            allowed[name].append(name+'_edge_finish')
    tolerance=H['boolean_fragment_max_volume_mm3']
    for name,mesh in raw.items():
        removed=exact_boolean([mesh,finished[name]],'difference')
        # Closed, validated inputs can produce exactly collapsed triangles in
        # this diagnostic difference (the production Boolean does the same cleanup).
        removed.update_faces(removed.area_faces>0.0)
        removed.remove_unreferenced_vertices()
        if len(removed.faces):removed.fix_normals(multibody=True)
        total=volume(removed)
        if allowed[name]:
            cutters=[load_tool(tool) for tool in allowed[name]]
            # Subtract permitted cutters from the full raw solid first. A tiny
            # diagnostic raw-minus-final sliver is not a sound Boolean input.
            cutter=cutters[0] if len(cutters)==1 else exact_boolean(cutters,'union')
            expected=exact_boolean([mesh,cutter],'difference')
            expected.update_faces(expected.area_faces>0.0)
            expected.remove_unreferenced_vertices();expected.fix_normals(multibody=True)
            unauthorized=exact_boolean([expected,finished[name]],'difference')
        else:
            unauthorized=removed
        lost=volume(unauthorized)
        results[name]={'removed_volume_mm3':total,'unauthorized_removed_volume_mm3':lost,
                       'allowed_tools':allowed[name],'passed':lost<=tolerance}
        print(name,results[name],flush=True)
    rings={}
    for side in ['left','right']:
        reference=trimesh.load_mesh(HYBRID/'ownership_reference'/f'hip_ring_{side}.stl')
        if 'torso' in finishing:
            reference=exact_boolean([reference,load_tool('torso_edge_finish')],'difference')
        missing_ring=volume(exact_boolean([reference,finished['torso']],'difference'))
        rings[side]={'owner':'torso','missing_volume_mm3':missing_ring,'passed':missing_ring<=tolerance}
    mounts={}
    if H.get('compact_socket_min_contact_mm3'):
        for spec in H['connections']:
            name=spec['name']
            if name not in H['preserve_anatomy_connections']:continue
            center=np.array(H[spec['center_key']],dtype=float)
            # Use an inscribed socket sphere, excluding every bridge; require
            # direct shell-to-original-torso contact, not just a connecting rod.
            if PARAMS['joint'].get('socket_profile'):
                shell=trimesh.load_mesh(HYBRID/'joint_tools'/f'{name}_socket_shell.stl')
            else:
                sphere=trimesh.creation.icosphere(subdivisions=4,radius=PARAMS['joint']['socket_outer_diameter_mm']/2)
                sphere.apply_translation(center)
                cut=trimesh.load_mesh(HYBRID/'joint_tools'/f'{name}_socket_cut.stl')
                shell=trimesh.boolean.difference([sphere,cut],engine='manifold')
            contact=volume(trimesh.boolean.intersection([raw['torso'],shell],engine='manifold'))
            mount={'direct_shell_torso_contact_mm3':contact,
                   'passed':contact>=H['compact_socket_min_contact_mm3']}
            if spec.get('source_support_mode')=='embedded_stem':
                endpoint=center+np.array(spec['mouth_direction'])*(PARAMS['joint']['ball_diameter_mm']/2+PARAMS['joint']['stud_reach_mm'])
                embedded=bool(raw[OWNERS[name][0]].contains([endpoint])[0])
                mount['stem_endpoint_inside_original_bone']=embedded
                mount['passed'] &= embedded
            mounts[name]=mount
    result={'source':str(INPUT.relative_to(ROOT)),'source_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),
            'scope':'Exact finite partition cuts; inverse rigid placement; final removal restricted to enabled machining and independently bounded edge-finish tools; hip rims remain torso-owned with only cut-border finishing permitted.',
            'tolerance_mm':H['preservation_tolerance_mm'],'volume_tolerance_mm3':tolerance,
            'overall':overall,'parts':results,'hip_rings':rings,'compact_mounts':mounts,'cut_edge_finishing':finishing,
            'passed':bool(overall['passed'] and all(p['passed'] for p in results.values()) and all(p['passed'] for p in rings.values()) and all(p['passed'] for p in mounts.values()))}
    # Cast NumPy booleans for the persisted audit.
    overall['passed']=bool(overall['passed'])
    report_path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)
    if not result['passed']:raise SystemExit(2)
