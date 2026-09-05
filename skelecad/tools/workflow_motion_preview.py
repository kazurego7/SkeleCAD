"""Immutable, non-printable motion previews with explicit joint readiness."""
import copy
import hashlib
import json
import shutil
import uuid
from pathlib import Path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(job, parts, joints, ready_parts, raw_directory, palette):
    """A ready joint requires both independently validated final endpoint meshes."""
    revision=uuid.uuid4().hex
    folder=job/'motion_previews'/revision
    folder.mkdir(parents=True)
    records=[]
    for index,name in enumerate(parts):
        source=raw_directory/(name+'.stl' if name in ready_parts else name+'_raw.stl')
        target=folder/(name+'.stl');shutil.copyfile(source,target)
        records.append({'name':name,'filename':target.name,'sha256':digest(target),
                        'label':f'パーツ {index+1}','color':palette[index%len(palette)],
                        'motion_ready':name in ready_parts,
                        'path':f'../api/jobs/{job.name}/files/v_{revision}_{name}.stl'})
    pending=copy.deepcopy(joints)
    for joint in pending:joint['motion_ready']=joint['parent'] in ready_parts and joint['part'] in ready_parts
    manifest={'schema_version':1,'id':job.name,'revision':revision,'stage':'motion_preview',
              'preview_only':True,'print_ready':False,'parts':records,'joints':pending,
              'ready_joint_count':sum(j['motion_ready'] for j in pending)}
    path=folder/'manifest.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'revision':revision,'manifest_sha256':digest(path),'ready_joint_count':manifest['ready_joint_count']}


def previous(job, state):
    """Reference the last fully checked assembly while a newer edit is processed."""
    import re
    try:
        current=json.loads((job/'manifest.json').read_text(encoding='utf-8'))
        source_sha=current.get('geometry',{}).get('sha256') or current.get('appearance_sha256')
        root=job/'machining'
        if not root.is_dir() or not source_sha:return None
        for folder in sorted((p for p in root.iterdir() if p.is_dir() and re.fullmatch('[0-9a-f]{32}',p.name)),key=lambda p:p.stat().st_mtime,reverse=True):
            status_path=folder/'status.json'
            if not status_path.is_file():continue
            status=json.loads(status_path.read_text(encoding='utf-8'))
            if status.get('stage')!='mechanical_review':continue
            manifest_path=folder/'manifest.json'
            if digest(manifest_path)!=status.get('manifest_sha256'):continue
            ready=json.loads(manifest_path.read_text(encoding='utf-8'))
            if ready.get('appearance_sha256')!=source_sha:continue
            source=json.loads((folder/'source_manifest.json').read_text(encoding='utf-8'))
            original={m['name']:m for m in source.get('joint_candidates',[])}
            markers=state.get('selected_markers')
            if markers is None:markers=current.get('joint_candidates',[])
            latest={m['name']:m for m in markers}
            fields=('center','radius_mm','symmetry_pair_id','placement_method')
            changed={name for name in original.keys()|latest.keys() if name not in original or name not in latest or any(original[name].get(k)!=latest[name].get(k) for k in fields)}
            regions=[{'center':m['center'],'radius_mm':m['radius_mm']} for mapping in (original,latest) for name,m in mapping.items() if name in changed]
            return {'revision':folder.name,'manifest_sha256':status['manifest_sha256'],
                    'changed_marker_names':sorted(changed),'changed_regions':regions}
    except (OSError,ValueError,KeyError,TypeError):return None
    return None
