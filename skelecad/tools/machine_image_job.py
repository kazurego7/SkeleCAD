"""Build an isolated mechanical revision from a closed image-derived mesh.

No automatic publication, approval or printing. The CLI is also the future web
worker entry. Failed revisions retain diagnostics and never replace a ready one.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from runtime_paths import tool_path
import numpy as np
import trimesh
from scipy.optimize import linear_sum_assignment

PROJECT=Path(__file__).resolve().parents[1]
WORKSPACE=PROJECT.parent
sys.path.insert(0,str(PROJECT/'src'))
from workflow_geometry import infer_branches
from finish_cut_edges import solid,from_solid,finish
from hybrid_apply_joints import weld_quantized_micro_boundaries


class MarkerMachiningError(ValueError):
    """A safe machining rejection tied to stable marker geometry, not display order."""
    def __init__(self,message,joints):
        super().__init__(message)
        self.marker_numbers=[int(j['marker_number']) for j in joints]
        self.marker_names=[j['name'] for j in joints]
        self.marker_locations=[{
            'center':[float(value) for value in j['center']],
            **({'symmetry_pair_id':j['symmetry_pair_id']} if j.get('symmetry_pair_id') else {})
        } for j in joints]


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    mesh=trimesh.load(path,force='mesh',process=True)
    if not mesh.is_volume:raise ValueError(f'Not a closed positive solid: {path.name}')
    return mesh


CACHE_SCHEMA_VERSION=1
AXIS_ALGORITHM_VERSION='batched_ray_grid_v2'


def value_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def save_solid_cache(path,value):
    if not value.is_volume:raise ValueError('Only a closed positive mesh can be cached')
    np.savez_compressed(path,vertices=np.asarray(value.vertices,dtype=np.float64),faces=np.asarray(value.faces,dtype=np.int64))
    return sha(path)


def load_solid_cache(path,expected_sha):
    if not path.is_file() or sha(path)!=expected_sha:raise ValueError('Cached geometry integrity mismatch')
    with np.load(path,allow_pickle=False) as data:
        mesh=trimesh.Trimesh(vertices=data['vertices'],faces=data['faces'],process=False)
    if not mesh.is_volume:raise ValueError('Cached geometry is not a closed positive solid')
    return mesh


def local_mesh_digest(mesh,center,radius):
    """Exact, order-independent geometry identity inside a conservative cube.

    The cube contains every possible axis ray used for this marker. Geometry
    outside it cannot affect axis/anchor placement and is deliberately excluded
    from the cache dependency.
    """
    center=np.asarray(center,dtype=np.float64);triangles=np.asarray(mesh.triangles,dtype=np.float64)
    lo=center-float(radius);hi=center+float(radius)
    keep=np.all(triangles.max(axis=1)>=lo,axis=1)&np.all(triangles.min(axis=1)<=hi,axis=1)
    triangles=triangles[keep]
    if len(triangles):
        # Same lexicographic order and float64 bytes as the per-face loop;
        # batch only the sorting, without rounding or resampling geometry.
        order=np.lexsort((triangles[:,:,2],triangles[:,:,1],triangles[:,:,0]),axis=1)
        canonical=np.asarray(np.take_along_axis(triangles,order[:,:,None],axis=1).reshape(-1,9),dtype='<f8')
        order=np.lexsort(tuple(canonical[:,i] for i in range(canonical.shape[1]-1,-1,-1)))
        payload=canonical[order].tobytes()
    else:payload=b''
    return hashlib.sha256(payload).hexdigest()


def previous_machining_cache(job,out,source_sha,settings_digest):
    root=job/'machining'
    if not root.is_dir():return None,None
    for directory in sorted((p for p in root.iterdir() if p.is_dir() and p!=out),key=lambda p:p.stat().st_mtime,reverse=True):
        path=directory/'machining_cache.json';status_path=directory/'status.json'
        if not path.is_file() or not status_path.is_file():continue
        try:status=json.loads(status_path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError) as exc:
            raise RuntimeError(f'保存済み加工状態を読み取れません（{directory.name}: {exc}）') from exc
        if status.get('stage')!='mechanical_review':continue
        try:data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError) as exc:
            raise RuntimeError(f'保存済み加工キャッシュを読み取れません（{directory.name}: {exc}）') from exc
        if (status.get('stage')=='mechanical_review' and data.get('schema_version')==CACHE_SCHEMA_VERSION and
            data.get('source_sha256')==source_sha and data.get('settings_digest')==settings_digest):return directory,data
    return None,None


def joint_cache_key(joint,meshes,cfg,symmetry_axis):
    radius=float(cfg['maximum_anchor_distance_mm'])+float(cfg['anchor_embed_mm'])+float(cfg['axis_anchor_sample_step_mm'])
    return value_digest({'algorithm':AXIS_ALGORITHM_VERSION,'name':joint['name'],'center':joint['center'],
        'radius_mm':joint['radius_mm'],'symmetry_pair_id':joint.get('symmetry_pair_id'),
        'placement_method':joint.get('placement_method'),'symmetry_axis':symmetry_axis,
        'parent_local_geometry':local_mesh_digest(meshes[joint['parent']],joint['center'],radius),
        'child_local_geometry':local_mesh_digest(meshes[joint['part']],joint['center'],radius),
        'axis_settings':{**{key:cfg[key] for key in ('anchor_embed_mm','axis_anchor_sample_step_mm','maximum_anchor_distance_mm',
                                                     'axis_search_step_deg','axis_search_max_angle_deg','axis_search_azimuth_step_deg')},
                         'axis_search_coarse_step_deg':cfg.get('axis_search_coarse_step_deg',float(cfg['axis_search_step_deg'])*3)}})


def apply_cached_joint(joint,entry,meshes):
    fields=('direction','parent_anchor','child_anchor','direction_adjustment_deg')
    if not all(field in entry for field in fields):raise ValueError('Cached joint record is incomplete')
    direction=np.asarray(entry['direction'],dtype=float);parent=np.asarray(entry['parent_anchor'],dtype=float);child=np.asarray(entry['child_anchor'],dtype=float)
    if not np.all(np.isfinite(np.r_[direction,parent,child])) or abs(np.linalg.norm(direction)-1)>1e-7:raise ValueError('Cached joint axis is invalid')
    center=np.asarray(joint['center'],dtype=float)
    if np.linalg.norm(np.cross(parent-center,direction))>1e-6 or np.linalg.norm(np.cross(child-center,direction))>1e-6:raise ValueError('Cached joint anchors are not collinear')
    if not meshes[joint['parent']].contains(parent.reshape(1,3))[0]:raise ValueError('Cached socket anchor is outside current anatomy')
    if not meshes[joint['part']].contains(child.reshape(1,3))[0]:raise ValueError('Cached ball anchor is outside current anatomy')
    for field in fields:joint[field]=copy.deepcopy(entry[field])
    if entry.get('direction_rule'):joint['direction_rule']=entry['direction_rule']
    joint['calculation_source']='validated_local_cache';return True


def cad(out,request):
    path=out/'request.json';write(path,request)
    result=subprocess.run([str(tool_path('freecad', 'python', WORKSPACE)),
                           str(PROJECT/'src/freecad_project.py'),'--workflow-tools',str(path)],
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (out/('cad_'+request['phase']+'.log')).write_bytes(result.stdout)
    if result.returncode:
        import locale
        try:detail=result.stdout.decode('utf-8')
        except UnicodeDecodeError:detail=result.stdout.decode(locale.getpreferredencoding(False),errors='replace')
        print(detail,flush=True)  # Preserve CAD output in the durable worker log too.
        lines=[line.strip() for line in detail.splitlines() if line.strip()]
        reason=lines[-1][:300] if lines else f'終了コード {result.returncode}'
        raise RuntimeError(f'CAD加工（{request["phase"]}）に失敗：{reason}')


def tree_joints(branches,candidates):
    cores={c['name']:c for c in branches['cores']};root=branches['root_candidate']
    if len(cores)!=len(candidates)+1:raise ValueError('Cuts do not form a single part tree; review candidates')
    adjacent={name:[] for name in cores}
    for c in candidates:
        if c['classification']!='two_part_junction':raise ValueError('Candidate does not connect exactly two parts')
        a,b=c['adjacent_cores'];adjacent[a].append((b,c));adjacent[b].append((a,c))
    queue=[root];visited={root};result=[]
    while queue:
        parent=queue.pop(0)
        for child,c in adjacent[parent]:
            if child in visited:continue
            visited.add(child);queue.append(child)
            result.append(dict(name=c['name'],parent=parent,part=child,center=c['center'],radius_mm=c['radius_mm'],
                               marker_number=c.get('marker_number'),symmetry_pair_id=c.get('symmetry_pair_id'),
                               placement_method=c.get('placement_method')))
    if visited!=set(cores):raise ValueError('Joint graph is cyclic or disconnected')
    return result


def apply_partition_cuts(source_solid,joints,cuts):
    """Apply cuts in visible marker order and record which step mis-splits.

    A tree joint must increase the number of connected solids by exactly one.
    Recording each step makes an aggregate component-count rejection actionable
    without ever publishing or discarding ambiguous anatomy.
    """
    raw=source_solid;steps=[]
    for joint in sorted(joints,key=lambda value:value['marker_number']):
        before=len(raw.decompose());raw=raw-solid(cuts[joint['name']]);after=len(raw.decompose())
        steps.append({'name':joint['name'],'marker_number':joint['marker_number'],
                      'components_before':before,'components_after':after,'component_delta':after-before})
    return raw,steps


def assign_marker_numbers(candidates):
    """Assign one visible number per marker group; bilateral members share it."""
    pair_numbers={};next_number=0
    for candidate in candidates:
        pair_id=candidate.get('symmetry_pair_id')
        if pair_id and pair_id in pair_numbers:
            candidate['marker_number']=pair_numbers[pair_id]
            continue
        next_number+=1;candidate['marker_number']=next_number
        if pair_id:pair_numbers[pair_id]=next_number
    return candidates


def choose_shell_relief(joints,clearances,minimum_wall):
    """Return the safer socket to relieve, or None if either cut is unsafe."""
    target=max(joints,key=lambda joint:clearances[joint['name']])
    return target if clearances[target['name']]+1e-6>=minimum_wall else None


def classify_hardware_interference(final,joints,tools,tolerance):
    """Allow exterior hardware overlap but protect every socket interior.

    External shell/stem intersections are not anatomy loss and do not justify
    moving an approved joint axis.  Anatomy-to-anatomy or hardware-to-anatomy
    overlap remains forbidden, as does any foreign solid entering a socket void.
    """
    hardware_by_part={name:None for name in final}
    for joint in joints:
        for part,kind in ((joint['socket_part'],'socket'),(joint['ball_part'],'ball')):
            hardware_by_part[part]=tools[joint['name']][kind] if hardware_by_part[part] is None else hardware_by_part[part]+tools[joint['name']][kind]
    collisions=[];allowed=[];names=list(final)
    for index,a in enumerate(names):
        for b in names[index+1:]:
            overlap=final[a]^final[b];volume=overlap.volume()
            if volume<=tolerance:continue
            permitted=None
            if hardware_by_part[a] is not None and hardware_by_part[b] is not None:
                permitted=overlap^(hardware_by_part[a]^hardware_by_part[b])
            permitted_volume=permitted.volume() if permitted is not None else 0.0
            forbidden=overlap-permitted if permitted is not None else overlap
            record={'a':a,'b':b,'volume_mm3':volume,'allowed_external_hardware_mm3':permitted_volume}
            if forbidden.volume()>tolerance:
                record['forbidden_volume_mm3']=forbidden.volume();collisions.append(record)
            else:allowed.append(record)
    intrusions=[]
    for socket_joint in joints:
        cavity=tools[socket_joint['name']]['cavity']
        for part,value in final.items():
            intrusion=value^cavity
            if part==socket_joint['socket_part']:
                intrusion=intrusion-tools[socket_joint['name']]['socket']
            if part==socket_joint['ball_part']:
                intrusion=intrusion-tools[socket_joint['name']]['ball']
            volume=intrusion.volume()
            if volume>tolerance:intrusions.append({'socket_joint':socket_joint['name'],'part':part,'volume_mm3':volume})
    return collisions,allowed,intrusions


def remove_boolean_micro_fragments(value,tolerance,label):
    """Discard only sub-tolerance kernel fragments; never hide a detached part."""
    components=value.decompose();kept=[];removed=[]
    for component in components:
        volume=float(component.volume())
        if abs(volume)<=tolerance:removed.append(volume)
        else:kept.append(component)
    if len(kept)!=1:
        raise ValueError(f'{label}: joint hardware is not connected to one anatomy part ({len(kept)} significant components)')
    return kept[0],removed


def interior_anchor(mesh,center,cfg):
    point,_,face=mesh.nearest.on_surface(np.array([center]))
    # At a cut-edge vertex, a single closest triangle normal can point through a
    # thin lip. Search neighbouring surface interiors, retaining the nearest
    # genuinely embedded anchor instead of accepting an outside attachment.
    from scipy.spatial import cKDTree
    _,ids=cKDTree(mesh.triangles_center).query(center,k=min(256,len(mesh.faces)))
    points=np.vstack((point,mesh.triangles_center[ids]))
    normals=np.vstack((mesh.face_normals[face],mesh.face_normals[ids]))
    anchors=points-normals*cfg['anchor_embed_mm']
    anchors=anchors[mesh.contains(anchors)]
    if not len(anchors):raise ValueError('Joint anchor not in solid material; move candidate')
    anchor=anchors[np.argmin(np.linalg.norm(anchors-center,axis=1))]
    if np.linalg.norm(anchor-center)>cfg['maximum_anchor_distance_mm']:
        raise ValueError('Joint attachment would be too long; move candidate')
    return anchor


def constrain_joint_directions(joints,symmetry_axis='x'):
    """Keep centre-plane axes straight and bilateral axes exactly mirrored."""
    axis_index={'x':0,'y':1,'z':2}.get(symmetry_axis)
    if axis_index is None:raise ValueError('Unsupported symmetry axis')
    for joint in joints:
        direction=np.asarray(joint['direction'],dtype=float)
        length=np.linalg.norm(direction)
        if length<1e-9:raise ValueError(f'{joint["name"]}: zero joint direction')
        joint['direction']=(direction/length).tolist()
    for joint in joints:
        if joint.get('placement_method')!='midline_plane_snap_v1':continue
        direction=np.asarray(joint['direction'],dtype=float);direction[axis_index]=0.0
        length=np.linalg.norm(direction)
        if length<1e-6:raise ValueError(f'{joint["name"]}: cannot determine a straight centre-plane joint axis')
        joint['direction']=(direction/length).tolist();joint['direction_rule']='centre_plane_straight_v1'
    pairs={}
    for joint in joints:
        if joint.get('symmetry_pair_id'):pairs.setdefault(joint['symmetry_pair_id'],[]).append(joint)
    for pair_id,members in pairs.items():
        if len(members)!=2:raise ValueError(f'{pair_id}: bilateral joint pair is incomplete')
        first,second=members;first_direction=np.asarray(first['direction'],dtype=float)
        reflected_second=np.asarray(second['direction'],dtype=float);reflected_second[axis_index]*=-1
        # The part tree may traverse the two mirrored edges in opposite
        # parent/child directions.  A joint axis is geometrically mirrored in
        # either case, but its vector must still point from parent to child so
        # the ray test probes the correct solid on each side.
        second_orientation=1.0
        if np.dot(first_direction,reflected_second)<0:
            reflected_second*=-1;second_orientation=-1.0
        shared=first_direction+reflected_second;length=np.linalg.norm(shared)
        if length<1e-6:raise ValueError(f'{pair_id}: cannot determine mirrored joint axes')
        shared/=length;mirrored=shared.copy();mirrored[axis_index]*=-1
        first['symmetry_direction_sign']=1.0;second['symmetry_direction_sign']=second_orientation
        first['direction']=shared.tolist();second['direction']=(mirrored*second_orientation).tolist()
        first['direction_rule']=second['direction_rule']='bilateral_mirror_v1'
    return joints


def ray_axis_anchors(mesh,center,directions,cfg):
    """Resolve many constrained anchors with one ray query per anatomy mesh.

    The returned anchors remain quantized to the configured sampling step, so
    this is an acceleration of the established placement rule rather than a
    lower-resolution approximation.  Final candidate anchors are independently
    checked independently with a point-in-solid predicate. Any ray backend
    failure is reported and never replaced by a different placement algorithm.
    """
    center=np.asarray(center,dtype=float);directions=np.asarray(directions,dtype=float)
    if directions.ndim==1:directions=directions.reshape(1,3)
    lengths=np.linalg.norm(directions,axis=1)
    if np.any(lengths<1e-12):raise ValueError('Zero joint direction')
    directions=directions/lengths[:,None]
    step=float(cfg['axis_anchor_sample_step_mm']);limit=float(cfg['maximum_anchor_distance_mm'])
    embed=float(cfg['anchor_embed_mm']);origins=np.repeat(center.reshape(1,3),len(directions),axis=0)
    try:
        locations,ray_ids,_=mesh.ray.intersects_location(origins,directions,multiple_hits=True)
    except Exception as exc:
        raise RuntimeError(f'ジョイント軸の光線交差計算に失敗しました（{exc}）') from exc
    hits=[[] for _ in directions]
    for location,ray_id in zip(locations,ray_ids):
        distance=float(np.dot(location-center,directions[int(ray_id)]))
        if distance>=-1e-8 and distance<=limit+step:hits[int(ray_id)].append(max(0.,distance))
    starts_inside=bool(mesh.contains(center.reshape(1,3))[0])
    anchors=[None]*len(directions);pending=[];pending_ids=[]
    for index,values in enumerate(hits):
        values=sorted(values);unique=[]
        for value in values:
            if not unique or value-unique[-1]>1e-7:unique.append(value)
        intervals=[]
        if starts_inside:
            if unique:intervals.append((0.,unique[0]))
            intervals.extend(zip(unique[1::2],unique[2::2]))
        else:intervals.extend(zip(unique[0::2],unique[1::2]))
        for entry,exit_distance in intervals:
            # A surface sample itself is not accepted as embedded.  This is the
            # same next-grid-point behaviour as the original contains loop.
            first=max(step,(np.floor(entry/step+1e-9)+1.)*step)
            target=first+embed
            anchor_distance=np.ceil(target/step-1e-9)*step
            if anchor_distance<=limit+1e-9 and anchor_distance<exit_distance-1e-8:
                pending_ids.append(index);pending.append(center+anchor_distance*directions[index]);break
    if pending:
        pending=np.asarray(pending);inside=np.asarray(mesh.contains(pending),dtype=bool)
        for index,point,valid in zip(pending_ids,pending,inside):
            if valid:anchors[index]=point
    return anchors


def axis_anchor(mesh,center,direction,cfg):
    """Find an embedded attachment or reject the unstable placement."""
    result=ray_axis_anchors(mesh,center,np.asarray(direction).reshape(1,3),cfg)[0]
    if result is not None:return result
    raise ValueError('ジョイント軸上に検証済みの埋め込み位置を作れません。マーカー位置を調整してください')


def _rotated_directions(base,max_angle_deg,step_deg,azimuth_step_deg,plane_axis=None):
    """Yield the smallest angular corrections first, optionally within one plane."""
    base=np.asarray(base,dtype=float);base/=np.linalg.norm(base)
    yield base,0.0
    angles=np.arange(step_deg,max_angle_deg+step_deg*.5,step_deg)
    if plane_axis is not None:
        axis=np.zeros(3);axis[plane_axis]=1.0
        for angle in angles:
            for signed in (angle,-angle):
                radians=np.deg2rad(signed)
                candidate=base*np.cos(radians)+np.cross(axis,base)*np.sin(radians)+axis*np.dot(axis,base)*(1-np.cos(radians))
                yield candidate/np.linalg.norm(candidate),abs(float(signed))
        return
    reference=np.array([1.,0.,0.]) if abs(base[0])<.8 else np.array([0.,1.,0.])
    tangent=np.cross(base,reference);tangent/=np.linalg.norm(tangent)
    bitangent=np.cross(base,tangent)
    azimuths=np.arange(0.,360.,azimuth_step_deg)
    for angle in angles:
        radians=np.deg2rad(angle)
        for azimuth in azimuths:
            phase=np.deg2rad(azimuth)
            radial=tangent*np.cos(phase)+bitangent*np.sin(phase)
            candidate=base*np.cos(radians)+radial*np.sin(radians)
            yield candidate/np.linalg.norm(candidate),float(angle)


def fit_constrained_joint_axes(joints,meshes,cfg,symmetry_axis='x'):
    """Find rotation-only axes that remain straight/mirrored and reach both parts."""
    axis_index={'x':0,'y':1,'z':2}.get(symmetry_axis)
    if axis_index is None:raise ValueError('Unsupported symmetry axis')
    step=float(cfg['axis_search_step_deg']);limit=float(cfg['axis_search_max_angle_deg'])
    coarse=float(cfg.get('axis_search_coarse_step_deg',step*3));azimuth=float(cfg['axis_search_azimuth_step_deg']);handled=set()

    def staged_indices(choices,valid):
        coarse_ids=[index for index,(_,angle) in enumerate(choices) if angle==0 or abs(angle/coarse-round(angle/coarse))<1e-9]
        first=valid(coarse_ids)
        if first is None:return list(range(len(choices)))
        bound=choices[first][1]
        return [index for index,(_,angle) in enumerate(choices) if angle<=bound+1e-9]

    anchor_cache={}
    def candidate_anchors(joint,directions):
        center=np.asarray(joint['center'],dtype=float);directions=np.asarray(directions,dtype=float)
        cache=anchor_cache.setdefault(joint['name'],{})
        keys=[direction.tobytes() for direction in directions]
        missing=[index for index,key in enumerate(keys) if key not in cache]
        if missing:
            subset=directions[missing]
            parent=ray_axis_anchors(meshes[joint['parent']],center,-subset,cfg)
            child=ray_axis_anchors(meshes[joint['part']],center,subset,cfg)
            for index,p,c in zip(missing,parent,child):cache[keys[index]]=(p,c)
        return [cache[key] for key in keys]

    pairs={}
    for joint in joints:
        if joint.get('symmetry_pair_id'):pairs.setdefault(joint['symmetry_pair_id'],[]).append(joint)
    for joint in joints:
        pair_id=joint.get('symmetry_pair_id')
        if pair_id:
            if pair_id in handled:continue
            members=pairs[pair_id];handled.add(pair_id)
            if len(members)!=2:raise ValueError(f'{pair_id}: bilateral joint pair is incomplete')
            first,second=members;base=np.asarray(first['direction'],dtype=float)
            choices=list(_rotated_directions(base,limit,step,azimuth));directions=np.asarray([choice[0] for choice in choices])
            reflected=directions.copy();reflected[:,axis_index]*=-1
            preferred_sign=float(second.get('symmetry_direction_sign',1.0));fitted=False
            def evaluate(indices,mirrored,commit=False):
                subset=directions[indices];mirrored_subset=mirrored[indices]
                try:first_results=candidate_anchors(first,subset);second_results=candidate_anchors(second,mirrored_subset)
                except RuntimeError as exc:raise MarkerMachiningError(f'マーカー{first["marker_number"]}番: {exc}',[first,second]) from exc
                for local,index in enumerate(indices):
                    first_anchors=first_results[local];second_anchors=second_results[local]
                    if any(value is None for value in first_anchors+second_anchors):continue
                    if not commit:return index
                    candidate,adjustment=choices[index];mirrored_candidate=mirrored[index]
                    for member,direction,result in ((first,candidate,first_anchors),(second,mirrored_candidate,second_anchors)):
                        member['direction']=direction.tolist();member['parent_anchor']=result[0].tolist();member['child_anchor']=result[1].tolist()
                        member['direction_adjustment_deg']=adjustment
                    return index
                return None
            # Both vector orientations describe the same mirrored axis line.
            # Test the preferred parent-to-child orientation first, then the
            # opposite tree orientation.  Neither option relaxes symmetry or
            # the point-in-solid validation.
            for orientation in (preferred_sign,-preferred_sign):
                mirrored=reflected*orientation
                indices=staged_indices(choices,lambda ids:evaluate(ids,mirrored))
                if evaluate(indices,mirrored,commit=True) is None:continue
                second['symmetry_direction_sign']=orientation;fitted=True;break
            if not fitted:raise MarkerMachiningError(f'マーカー{first["marker_number"]}番: 光線交差で検証済みの左右対称軸を決定できません。マーカー位置または接続形状を確認してください',[first,second])
            continue
        base=np.asarray(joint['direction'],dtype=float)
        plane_axis=axis_index if joint.get('direction_rule')=='centre_plane_straight_v1' else None
        choices=list(_rotated_directions(base,limit,step,azimuth,plane_axis));directions=np.asarray([choice[0] for choice in choices])
        def evaluate(indices,commit=False):
            try:results=candidate_anchors(joint,directions[indices])
            except RuntimeError as exc:raise MarkerMachiningError(f'マーカー{joint["marker_number"]}番: {exc}',[joint]) from exc
            for local,index in enumerate(indices):
                result=results[local]
                if any(value is None for value in result):continue
                if not commit:return index
                candidate,adjustment=choices[index]
                joint['direction']=candidate.tolist();joint['parent_anchor']=result[0].tolist();joint['child_anchor']=result[1].tolist()
                joint['direction_adjustment_deg']=adjustment;return index
            return None
        indices=staged_indices(choices,evaluate)
        if evaluate(indices,commit=True) is not None:pass
        else:raise MarkerMachiningError(f'マーカー{joint["marker_number"]}番: 光線交差で検証済みの回転軸を決定できません。マーカー位置を調整してください',[joint])
    return joints


def export_print_mesh(value,path,printing,volume_tolerance):
    # Validate the actual float32 STL, not only the kernel's internal float64 mesh.
    tolerance=printing['stl_quantization_cleanup_mm']
    internal=value.simplify(tolerance).to_mesh64()
    mesh=trimesh.Trimesh(internal.vert_properties[:,:3],internal.tri_verts,process=False)
    mesh=trimesh.load(io.BytesIO(mesh.export(file_type='stl')),file_type='stl',process=True)
    mesh.update_faces(mesh.area_faces>0);mesh.update_faces(mesh.unique_faces());mesh.remove_unreferenced_vertices()
    mesh=weld_quantized_micro_boundaries(mesh,tolerance,path.stem)
    components=mesh.split(only_watertight=False)
    removed=[]
    if len(components)>1:
        significant=[]
        for component in components:
            component_volume=abs(float(component.volume))
            if component.is_volume and component_volume<=volume_tolerance:
                removed.append(component_volume)
            else:
                significant.append(component)
        # STL quantisation can turn a zero-volume Boolean sliver into a closed
        # tetrahedron. Remove only certified closed fragments below the fixed
        # Boolean-volume threshold; never loosen the tolerance or discard an
        # open/significant component.
        if len(significant)==1 and removed:
            mesh=significant[0]
            mesh.remove_unreferenced_vertices()
    components=len(mesh.split(only_watertight=False))
    diagnostic={'tolerance_mm':tolerance,'watertight':bool(mesh.is_watertight),'winding':bool(mesh.is_winding_consistent),
                'volume':bool(mesh.is_volume),'components':components,
                'removed_closed_micro_fragments_mm3':removed}
    if not mesh.is_volume or components!=1:
        raise ValueError(f'出力STLのトポロジーが不正です（{path.name}: {diagnostic}）。許容差を変更した再試行は行いません')
    mesh.export(path);actual=load(path)
    delta=abs(actual.volume-value.volume())
    if delta>volume_tolerance:raise ValueError(f'出力STLの体積が変化しました（{path.name}: {delta} mm3）')
    return actual,{'sha256':sha(path),'faces':len(actual.faces),'watertight':True,'components':1,
                   'volume_mm3':float(actual.volume),'export_volume_error_mm3':delta,
                   'removed_closed_micro_fragments_mm3':removed}


def changed_joint_names(job):
    """Prioritize edited markers without changing geometry or acceptance rules."""
    try:
        current=json.loads((job/'manifest.json').read_text(encoding='utf-8'))
        revision=current.get('partition_review',{}).get('revision','')
        if len(revision)!=32 or any(c not in '0123456789abcdef' for c in revision):return []
        previous=json.loads((job/'partition'/revision/'source_manifest.json').read_text(encoding='utf-8'))
        old={m['name']:m for m in previous.get('joint_candidates',[])}
        fields=('center','radius_mm','symmetry_pair_id','placement_method')
        return [m['name'] for m in current.get('joint_candidates',[]) if
                m['name'] not in old or any(m.get(k)!=old[m['name']].get(k) for k in fields)]
    except (OSError,ValueError,KeyError,TypeError):return []


def machine(job, selected=None, cancelled=None, priority_markers=None, progress=None):
    started=time.perf_counter();timings={};stage_started=started
    def checkpoint():
        if cancelled and cancelled():raise InterruptedError('Newer workflow inputs superseded this calculation')
    def stage(name):
        nonlocal stage_started
        moment=time.perf_counter();timings[name]=moment-stage_started;stage_started=moment
        checkpoint()
    checkpoint()
    if priority_markers is None:priority_markers=changed_joint_names(job)
    params=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))
    manifest=json.loads((job/'manifest.json').read_text(encoding='utf-8'))
    source=job/'appearance.stl'
    if sha(source)!=manifest['geometry']['sha256']:raise ValueError('Appearance hash mismatch')
    if manifest['id']!=job.name:raise ValueError('Wrong job manifest')
    candidates=assign_marker_numbers(copy.deepcopy(manifest['joint_candidates']))
    if selected is not None:
        if not selected or len(set(selected))!=len(selected):raise ValueError('Empty or duplicate joint selection')
        if set(selected)-{c['name'] for c in candidates}:raise ValueError('Unknown joint selection')
        candidates=[c for c in candidates if c['name'] in selected]
    else:candidates=[c for c in candidates if c['classification']=='two_part_junction']
    if not candidates:raise ValueError('No two-part joints; candidate correction is required')
    detector=manifest['joint_detection'];cfg=params['image_workflow']['manufacturing']
    mesh=load(source);branches=infer_branches(mesh,candidates,detector);joints=tree_joints(branches,candidates)
    revision=uuid.uuid4().hex;out=job/'machining'/revision;out.mkdir(parents=True)
    status={'revision':revision,'stage':'building','source_sha256':sha(source),'print_ready':False}
    write(out/'status.json',status)
    try:
        request={'phase':'cut','settings':{'manufacturing':cfg,'cut_edge_finish':params['hybrid_new']['cut_edge_finish'],
                                          'printing':params['printing']},'trial_parameters':params['joint_retention_trial'],'joints':joints}
        settings_digest=value_digest({'request_settings':request['settings'],'trial_parameters':request['trial_parameters'],
                                      'detector':detector,'cache_schema':CACHE_SCHEMA_VERSION})
        cache_directory,cache=previous_machining_cache(job,out,sha(source),settings_digest)
        cache=cache or {'parts':{},'joints':{}}
        cache_report={'schema_version':CACHE_SCHEMA_VERSION,'source_sha256':sha(source),'settings_digest':settings_digest,
                      'parts':{},'joints':{},'reused_parts':0,'reused_joints':0}
        write(out/'source_manifest.json',manifest)
        for j in joints:j['cut_radius_mm']=j['radius_mm']*detector['branch_envelope_ratio']
        cad(out,request)
        stage('cut_tool_cad_seconds')
        cuts={j['name']:load(out/'tools'/(j['name']+'_cut.stl')) for j in joints}
        source_solid=solid(mesh);raw,cut_steps=apply_partition_cuts(source_solid,joints,cuts)
        components=[from_solid(c,clean_faces=False) for c in raw.decompose()]
        write(out/'partition.json',{'expected':len(branches['cores']),'actual':len(components),
                                   'volumes_mm3':[float(m.volume) for m in components],'marker_steps':cut_steps})
        if len(components)!=len(branches['cores']):
            failed_numbers={step['marker_number'] for step in cut_steps if step['component_delta']!=1}
            failed=[joint for joint in joints if joint['marker_number'] in failed_numbers] or joints
            numbers='・'.join(str(number) for number in sorted({joint['marker_number'] for joint in failed}))
            failed_steps=[step for step in cut_steps if step['marker_number'] in failed_numbers]
            detail='、'.join(f'{step["marker_number"]}番: {step["components_before"]}→{step["components_after"]}' for step in failed_steps)
            raise MarkerMachiningError(
                f'マーカー{numbers}番の切断で、部品数が1つだけ増える想定に合いません（{detail}）。'
                f'位置または分割範囲を調整してください（想定 {len(branches["cores"])}部品／結果 {len(components)}部品）。'
                '元の形状は変更していません。',failed)
        # Seed matching is global one-to-one, not first-match / largest-part guessing.
        seeds=np.array([c['surface_seed'] for c in branches['cores']])
        distances=np.array([m.nearest.on_surface(seeds)[1] for m in components]).T
        rows,columns=linear_sum_assignment(distances)
        if np.max(distances[rows,columns])>.05:raise ValueError('Closed parts do not match the inferred cores')
        parts={branches['cores'][r]['name']:components[c] for r,c in zip(rows,columns)}
        stage('partition_seconds')
        finished={};records_by_part={};removals_by_part={};part_cache_keys={}
        timings['edge_finish_seconds']=0.0;timings['axis_and_anchor_seconds']=0.0
        def finish_part(name):
            if name in finished:return
            checkpoint();begin=time.perf_counter();part=parts[name]
            try:
                print('Finishing',name,flush=True)
                nearby=[cuts[j['name']] for j in joints if name in (j['parent'],j['part'])]
                raw_path=out/(name+'_raw.stl');part.export(raw_path)
                part_key=value_digest({'raw_sha256':sha(raw_path),'cut_sha256':sorted(sha(out/'tools'/(j['name']+'_cut.stl'))
                                      for j in joints if name in (j['parent'],j['part'])),
                                      'finish':params['hybrid_new']['cut_edge_finish'],'strengths':cfg['finish_strengths']})
                part_cache_keys[name]=part_key;cached=cache.get('parts',{}).get(part_key);removal=None;seams=np.empty((0,2),dtype=np.int64)
                if cached and cache_directory:
                    try:
                        result=load_solid_cache(cache_directory/cached['finished_file'],cached['finished_sha256'])
                        record=copy.deepcopy(cached['record']);record['part']=name;record['cache_reused']=True
                        if cached.get('removal_file'):
                            removal_path=cache_directory/cached['removal_file']
                            if sha(removal_path)!=cached['removal_sha256']:raise ValueError('Cached removal integrity mismatch')
                            with np.load(removal_path,allow_pickle=False) as data:
                                removal=trimesh.Trimesh(vertices=data['vertices'],faces=data['faces'],process=False);seams=data['seams']
                            if not removal.is_volume:raise ValueError('Cached removal is not a solid')
                        cache_report['reused_parts']+=1
                    except (OSError,KeyError,ValueError) as exc:
                        raise ValueError(f'{name}: validated finish cache cannot be reused: {exc}') from exc
                if not cached:
                    strengths=cfg['finish_strengths']
                    if len(strengths)!=1:
                        raise ValueError(f'{name}: 切断面仕上げ条件は1つだけ指定してください（現在 {strengths}）。自動フォールバックは行いません')
                    strength=float(strengths[0]);finish_cfg=dict(params['hybrid_new']['cut_edge_finish'])
                    finish_cfg['relaxation']*=strength;finish_cfg['max_displacement_mm']*=strength
                    try:
                        result,removal,record,seams=finish(part,nearby,finish_cfg,name,
                                                          fragment_tolerance=cfg['boolean_volume_tolerance_mm3'])
                    except RuntimeError as exc:
                        raise ValueError(f'{name}: 指定条件で切断面を安全に仕上げられません（{exc}）。条件を変えた再試行は行いません') from exc
                    record.update(strength=strength,cache_reused=False)
                finished_file=name+'_finished.npz';finished_sha=save_solid_cache(out/finished_file,result)
                cache_entry={'finished_file':finished_file,'finished_sha256':finished_sha,'record':record}
                if removal is not None:
                    removals_by_part[name]=solid(removal)
                    removal_file=name+'_finish_removal.npz';np.savez_compressed(out/removal_file,vertices=removal.vertices,faces=removal.faces,seams=seams)
                    cache_entry.update(removal_file=removal_file,removal_sha256=sha(out/removal_file))
                cache_report['parts'][part_key]=cache_entry
                records_by_part[name]=record;finished[name]=result
            finally:timings['edge_finish_seconds']+=time.perf_counter()-begin
        symmetry_axis=params['image_workflow']['partition_review']['symmetry_mirroring'].get('axis','x')
        pairs={}
        for joint in joints:
            group=joint.get('symmetry_pair_id') or joint['name'];pairs.setdefault(group,[]).append(joint)
        priority=set(priority_markers or [])
        groups=sorted(pairs.values(),key=lambda members:not any(j['name'] in priority for j in members))
        keys={}
        for members in groups:
            checkpoint()
            for member in members:
                for name in (member['parent'],member['part']):finish_part(name)
            begin=time.perf_counter()
            try:
                for member in members:keys[member['name']]=joint_cache_key(member,finished,cfg,symmetry_axis)
                entries=[cache.get('joints',{}).get(keys[member['name']]) for member in members]
                if all(entries):
                    try:
                        for member,entry in zip(members,entries):apply_cached_joint(member,entry,finished)
                    except ValueError as exc:raise MarkerMachiningError(f'マーカー{members[0]["marker_number"]}番: 保存済みジョイントの再検証に失敗しました（{exc}）',members) from exc
                    cache_report['reused_joints']+=len(members)
                else:
                    for j in members:
                        center=np.array(j['center'])
                        print('Anchoring',j['name'],j['parent'],j['part'],flush=True)
                        j['parent_anchor']=interior_anchor(finished[j['parent']],center,cfg).tolist()
                        child=interior_anchor(finished[j['part']],center,cfg)
                        j['child_anchor']=child.tolist();direction=child-center;direction/=np.linalg.norm(direction)
                        j['direction']=direction.tolist()
                    constrain_joint_directions(members,symmetry_axis)
                    fit_constrained_joint_axes(members,finished,cfg,symmetry_axis)
            finally:timings['axis_and_anchor_seconds']+=time.perf_counter()-begin
        for name in parts:finish_part(name)
        # Preserve export, boolean and audit ordering regardless of validation order.
        finished={name:finished[name] for name in parts}
        records=[records_by_part[name] for name in parts]
        removals=[removals_by_part[name] for name in parts if name in removals_by_part]
        write(out/'edge_finish.json',records)
        stage_started=time.perf_counter()
        for j in joints:
            if 'calculation_source' not in j:j['calculation_source']=AXIS_ALGORITHM_VERSION
            j['socket_part']=j['parent'];j['ball_part']=j['part']
            j['socket_anchor']=j['parent_anchor'];j['ball_anchor']=j['child_anchor'];j['tool_direction']=j['direction']
            cache_report['joints'][keys[j['name']]]={field:copy.deepcopy(j[field]) for field in
                ('direction','parent_anchor','child_anchor','direction_adjustment_deg')}
            if j.get('direction_rule'):cache_report['joints'][keys[j['name']]]['direction_rule']=j['direction_rule']
        checkpoint()
        request['phase']='joint';cad(out,request)
        stage('joint_tool_cad_seconds')
        values={name:solid(m) for name,m in finished.items()}
        tools={}
        for j in joints:
            prefix=out/'tools'/j['name']
            tools[j['name']]={kind:solid(load(Path(str(prefix)+'_'+kind+'.stl'))) for kind in ('socket','shell','void','cavity','ball')}
        socket_values={j['name']:tools[j['name']]['socket'] for j in joints}
        tolerance=cfg['boolean_volume_tolerance_mm3']
        for j in joints:
            values[j['socket_part']]=values[j['socket_part']]+socket_values[j['name']]
            values[j['ball_part']]=values[j['ball_part']]+tools[j['name']]['ball']
        fragment_cleanup=[]
        for name,value in list(values.items()):
            values[name],removed=remove_boolean_micro_fragments(value,tolerance,name)
            if removed:fragment_cleanup.append({'part':name,'removed_signed_volumes_mm3':removed})
        write(out/'hardware_trim.json',{'scope':'no exterior hardware relief; joint centres and axes preserved',
             'policy':'exterior socket/stem overlap allowed; socket interior intrusion rejected',
             'socket_shell_reliefs':[],'socket_bridge_reliefs':[],'sub_tolerance_boolean_fragments':fragment_cleanup})
        final={};part_records=[]
        palette=[p['color'] for p in manifest['parts']]
        canonical_names=list(values)
        root_names=[name for name in values if name not in {j['part'] for j in joints}]
        export_names=list(dict.fromkeys([*root_names,*(j['part'] for j in joints),*canonical_names])) if progress else canonical_names
        for name in export_names:
            index=canonical_names.index(name);value=values[name]
            actual,record=export_print_mesh(value,out/(name+'.stl'),params['printing'],cfg['boolean_volume_tolerance_mm3'])
            final[name]=solid(actual)
            part_records.append(dict(record,name=name,label=f'パーツ {index+1}',color=palette[index%len(palette)],filename=name+'.stl'))
            if progress and any(j['parent'] in final and j['part'] in final for j in joints):
                checkpoint()
                from workflow_motion_preview import emit
                progress(emit(job,list(parts),joints,set(final),out,palette))
        final={name:final[name] for name in canonical_names}
        part_records.sort(key=lambda record:canonical_names.index(record['name']))
        stage('hardware_union_and_export_seconds')
        collisions,allowed_hardware_overlaps,interior_intrusions=classify_hardware_interference(final,joints,tools,tolerance)
        names=list(final);write(out/'collision.json',{'pairs_checked':len(names)*(len(names)-1)//2,
            'collisions':collisions,'allowed_external_hardware_overlaps':allowed_hardware_overlaps,
            'socket_interior_intrusions':interior_intrusions})
        if interior_intrusions:
            failed_names={item['socket_joint'] for item in interior_intrusions};failed=[joint for joint in joints if joint['name'] in failed_names]
            numbers='・'.join(str(number) for number in sorted({joint['marker_number'] for joint in failed}))
            raise MarkerMachiningError(f'マーカー{numbers}番のソケット内側に別パーツが入り込んでいます。外側の重なりは許容しています。',failed)
        if collisions:raise ValueError('Neutral assembly collides; revise placement before publication')
        # Independent source-volume preservation outside finite cuts and finish tubes.
        unexplained=source_solid
        for value in final.values():unexplained=unexplained-value
        for tool in cuts.values():unexplained=unexplained-solid(tool)
        for removal in removals:unexplained=unexplained-removal
        lost=unexplained.volume()
        if lost>cfg['boolean_volume_tolerance_mm3']:raise ValueError(f'Unexplained anatomy loss {lost} mm3')
        stage('collision_and_preservation_audit_seconds')
        result={'schema_version':1,'id':job.name,'revision':revision,'stage':'mechanical_review',
                'name':manifest['name'],'source_sha256':manifest['source_sha256'],'appearance_sha256':sha(source),
                'parts':part_records,'joints':joints,'print_ready':False,'settings':request['settings'],
                'unexplained_removed_volume_mm3':lost,'physical_fit_verified':False,
                'limitations':['Experimental C4 joint: physical retention and fatigue unverified.',
                               'Organic wall thickness and attachment strength still require checks.']}
        write(out/'manifest.json',result)
        doc_run=subprocess.run([str(tool_path('freecad', 'python', WORKSPACE)),
                                str(PROJECT/'src/freecad_project.py'),'--workflow-assembly',str(out)],
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (out/'assembly_document.log').write_bytes(doc_run.stdout)
        if doc_run.returncode:raise ValueError('Assembly document export failed')
        stage('assembly_document_seconds');timings['total_seconds']=time.perf_counter()-started
        cache_report['source_revision']=cache_directory.name if cache_directory else None
        write(out/'machining_cache.json',cache_report);write(out/'performance.json',timings)
        status.update(stage='mechanical_review',manifest_sha256=sha(out/'manifest.json'))
    except Exception as exc:
        timings['failed_after_seconds']=time.perf_counter()-started;timings['error']=str(exc)
        write(out/'performance.json',timings)
        status.update(stage='failed',error=str(exc));write(out/'status.json',status);raise
    write(out/'status.json',status)
    print(str(out),flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job-directory',type=Path,required=True)
    parser.add_argument('--joints',nargs='+');args=parser.parse_args()
    machine(args.job_directory.resolve(),args.joints)
