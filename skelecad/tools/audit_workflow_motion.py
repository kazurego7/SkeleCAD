"""Actual exported part interference, one joint at a time with descendants.

Discrete rigid checks only: not contact mechanics, continuous motion or a
holding-force test. Read geometry from disk and verify its recorded hash first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh
from machine_image_job import PROJECT,load,solid,write,classify_hardware_interference


def moving_parts(joints,part):
    result={part}
    while True:
        larger=result|{j['part'] for j in joints if j['parent'] in result}
        if larger==result:return result
        result=larger


def pose_matrices(joints,pose):
    """Match motion-core.js, including its accepted cardinal-axis gestures."""
    local={};parents={j['part']:j['parent'] for j in joints};world={};visiting=set()
    if set(pose)!={j['name'] for j in joints}:raise ValueError('Incomplete reviewed pose')
    for j in joints:
        d=np.array(j['direction'],dtype=float);d/=np.linalg.norm(d)
        if abs(d[1])>1-1e-12:axes=([d[1],0,0],[0,0,-d[1]],d)
        elif abs(d[0])>1-1e-12:axes=([0,-d[0],0],[0,0,1],d)
        elif abs(d[2])>1-1e-12:axes=([1,0,0],[0,1,0],d)
        else:
            ref=np.array([1,0,0] if abs(d[0])<.8 else [0,1,0]);a=ref-np.dot(ref,d)*d;a/=np.linalg.norm(a)
            axes=(a,np.cross(d,a),d)
        angles=pose[j['name']]
        if not isinstance(angles,list) or len(angles)!=3 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and np.isfinite(v) and abs(v)<=60 for v in angles):
            raise ValueError('Invalid reviewed angles')
        matrix=np.eye(4)
        for axis,angle in zip(axes,angles):matrix=trimesh.transformations.rotation_matrix(np.radians(angle),axis,j['center'])@matrix
        local[j['part']]=matrix
    def resolve(part):
        if part in world:return world[part]
        if part in visiting:raise ValueError('Cyclic joint graph')
        visiting.add(part)
        world[part]=resolve(parents[part])@local[part] if part in parents else np.eye(4)
        visiting.remove(part);return world[part]
    for part in parents:resolve(part)
    return world


def load_posed_tools(directory,joints,matrices):
    tools={}
    for joint in joints:
        prefix=directory/'tools'/joint['name']
        tools[joint['name']]={}
        for kind in ('socket','shell','void','cavity','ball'):
            owner=joint['ball_part'] if kind=='ball' else joint['socket_part']
            tools[joint['name']][kind]=solid(load(Path(str(prefix)+'_'+kind+'.stl'))).transform(
                matrices.get(owner,np.eye(4))[:3,:])
    return tools


def verify_review_pose(directory,pose):
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    matrices=pose_matrices(manifest['joints'],pose);parts={}
    for spec in manifest['parts']:
        path=directory/spec['filename']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=spec['sha256']:raise ValueError('Reviewed geometry changed')
        parts[spec['name']]=solid(load(path)).transform(matrices.get(spec['name'],np.eye(4))[:3,:])
    tolerance=manifest['settings']['manufacturing']['boolean_volume_tolerance_mm3']
    tools=load_posed_tools(directory,manifest['joints'],matrices)
    collisions,allowed,intrusions=classify_hardware_interference(parts,manifest['joints'],tools,tolerance)
    clear=not collisions and not intrusions
    write(directory/'review_pose_audit.json',{'pose':pose,'collisions':collisions,
          'allowed_external_hardware_overlaps':allowed,'socket_interior_intrusions':intrusions,'clear':clear})
    if not clear:raise ValueError('確認した姿勢で骨またはソケット内側に食い込みがあります。姿勢を戻して確認してください。')
    return True


def audit(directory):
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    cfg=manifest['settings']['manufacturing'];parts={};topology=[]
    for spec in manifest['parts']:
        path=directory/spec['filename']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=spec['sha256']:raise ValueError('Part hash mismatch')
        mesh=load(path)
        if len(mesh.split(only_watertight=False))!=1:raise ValueError('Disconnected part')
        parts[spec['name']]=solid(mesh)
        topology.append({'name':spec['name'],'closed':True,'positive_volume':True,'components':1})
    checks=[];tolerance=cfg['boolean_volume_tolerance_mm3']
    for j in manifest['joints']:
        d=np.array(j['direction']);d/=np.linalg.norm(d)
        ref=np.eye(3)[np.argmin(np.abs(d))];a=np.cross(d,ref);a/=np.linalg.norm(a);b=np.cross(d,a)
        moving=moving_parts(manifest['joints'],j['part']);fixed=set(parts)-moving
        sweeps=[]
        for az in np.linspace(0,2*np.pi,cfg['motion_azimuth_count'],endpoint=False):
            axis=np.cos(az)*a+np.sin(az)*b;last=0.;collision=None
            for angle in np.arange(cfg['motion_sample_step_deg'],cfg['motion_sample_limit_deg']+1e-9,cfg['motion_sample_step_deg']):
                matrix=trimesh.transformations.rotation_matrix(np.radians(angle),axis,j['center'])[:3,:]
                matrices={name:(np.vstack((matrix,[0,0,0,1])) if name in moving else np.eye(4)) for name in parts}
                posed={name:value.transform(matrices[name][:3,:]) for name,value in parts.items()}
                posed_tools=load_posed_tools(directory,manifest['joints'],matrices)
                collisions,allowed,intrusions=classify_hardware_interference(posed,manifest['joints'],posed_tools,tolerance)
                if collisions or intrusions:
                    collision={'angle_deg':float(angle),'collisions':collisions,'socket_interior_intrusions':intrusions,
                               'allowed_external_hardware_overlaps':allowed}
                if collision:break
                last=float(angle)
            sweeps.append({'azimuth_deg':float(np.degrees(az)),'last_clear_sample_deg':last,'first_collision':collision})
        checks.append({'joint':j['name'],'moving_parts':sorted(moving),'sweeps':sweeps,
                       'minimum_clear_sample_deg':min(s['last_clear_sample_deg'] for s in sweeps)})
        print(j['name'],checks[-1]['minimum_clear_sample_deg'],flush=True)
    report={'manifest_sha256':hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
            'topology':topology,'joints':checks,'parameters':cfg,
            'scope':'Discrete whole-assembly rigid Boolean checks, single joint plus descendants; external hardware overlap allowed, socket interiors and anatomy protected; no physical fit or continuous-motion guarantee.'}
    write(directory/'motion_audit.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--revision-directory',type=Path,required=True)
    audit(parser.parse_args().revision_directory.resolve())
