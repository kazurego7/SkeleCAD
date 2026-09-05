"""Build and publish one exact YZ-symmetric appearance revision."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
import traceback
import uuid
from pathlib import Path

import trimesh

from workflow_store import PROJECT, now, process_identity, write_json


def atomic_copy(source, target):
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    shutil.copy2(source,temporary);os.replace(temporary,target)


def run(directory):
    state_path=directory/'state.json';state=json.loads(state_path.read_text(encoding='utf-8'))
    def update(**fields):state.update(updated_at=now(),**fields);write_json(state_path,state)
    update(stage='symmetrizing',message='選んだ側を基準に、YZ面で左右を揃えています',pid=os.getpid(),process_identity=process_identity(os.getpid()))
    try:
        manifest_path=directory/'manifest.json';appearance=directory/'appearance.stl'
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=state['source_manifest_sha256']:
            raise ValueError('左右対称化の元モデルが更新されています。')
        current_manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if hashlib.sha256(appearance.read_bytes()).hexdigest()!=current_manifest['geometry']['sha256']:
            raise ValueError('左右対称化の元形状を照合できません。')

        original=directory/'symmetry'/'original';original.mkdir(parents=True,exist_ok=True)
        record_path=original/'record.json'
        if not record_path.exists():
            atomic_copy(appearance,original/'appearance.stl');atomic_copy(manifest_path,original/'manifest.json')
            record={'appearance_sha256':hashlib.sha256((original/'appearance.stl').read_bytes()).hexdigest(),
                    'manifest_sha256':hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest(),
                    'preview_part_count':state.get('preview_part_count'),
                    'partition_revision':state.get('partition_revision'),
                    'selected_markers':state.get('selected_markers'),
                    'selected_joints':state.get('selected_joints')}
            write_json(record_path,record)
        else:
            record=json.loads(record_path.read_text(encoding='utf-8'))
            if (hashlib.sha256((original/'appearance.stl').read_bytes()).hexdigest()!=record['appearance_sha256'] or
                    hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest()!=record['manifest_sha256']):
                raise ValueError('保存した元形状を照合できません。')

        source_side=state['symmetry_source_side'];revision=uuid.uuid4().hex
        revision_dir=directory/'symmetry'/revision;revision_dir.mkdir(parents=True)
        sys.path.insert(0,str(PROJECT/'src'))
        from workflow_symmetry import geometry_report,symmetrize_yz
        source=trimesh.load(original/'appearance.stl',force='mesh',process=True)
        result=symmetrize_yz(source,source_side)
        candidate=revision_dir/'appearance.stl';result.export(candidate)
        # Re-open the float32 STL: downstream CAD receives exactly this topology.
        result=trimesh.load(candidate,force='mesh',process=True)
        if not result.is_volume:raise ValueError('STL保存後の左右対称形状が閉じていません。')
        baseline=json.loads((original/'manifest.json').read_text(encoding='utf-8'))
        report=geometry_report(result,candidate,baseline.get('geometry'),source_side)

        from workflow_geometry import analyse
        parameters=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']['joint_detection']
        candidates=analyse(candidate,revision_dir/'joint_candidates.json',parameters)
        preview=candidates['partition_preview'];base=f'../api/jobs/{state["id"]}/files/'
        prefix='preview_'+revision
        if preview:
            # analyse writes local generic names; publish unique names so the old
            # manifest remains fully restorable and browser reads are atomic.
            parts=[]
            for index,part in enumerate(preview['parts']):
                filename=f'{prefix}_part_{index:02d}.stl';target=directory/filename
                atomic_copy(revision_dir/part['filename'],target)
                part={**part,'filename':filename,'path':base+filename,
                      'sha256':hashlib.sha256(target.read_bytes()).hexdigest()};parts.append(part)
            preview={**preview,'parts':parts}
        else:
            parts=[{'name':'appearance','label':'左右対称化した外観','color':'#cbb98e','path':base+'appearance.stl','sha256':report['sha256']}]
        manifest=copy.deepcopy(baseline)
        manifest.update(stage='partition_preview' if preview else 'appearance_review',parts=parts,partition_preview=preview,
                        joints=[],joint_candidates=candidates['candidates'],branch_graph=candidates['branch_graph'],
                        joint_detection=parameters,geometry=report,print_ready=False,
                        appearance_symmetry={'active':True,'plane':'YZ','source_side':source_side,'revision':revision})
        manifest.pop('partition_review',None)
        write_json(revision_dir/'manifest.json',manifest)
        # The visible pair changes only after all geometry and analysis checks pass.
        atomic_copy(candidate,appearance);atomic_copy(revision_dir/'manifest.json',manifest_path)
        digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        label='右側' if source_side=='positive_x' else '左側'
        for key in ('error','partition_revision','mechanical_revision','prints','selected_markers','selected_joints','failed_marker_numbers','failed_marker_names','failed_marker_locations'):
            state.pop(key,None)
        update(stage='appearance_ready',operation='symmetry',message=f'{label}を基準にYZ面で左右対称化しました。分割位置を指定できます。',
               manifest=base+'manifest.json',manifest_sha256=digest,preview_part_count=len(parts),
               appearance_symmetry={'active':True,'plane':'YZ','source_side':source_side,'revision':revision})
    except Exception as exc:
        traceback.print_exc();update(stage='symmetry_failed',message='左右対称化に失敗しました。表示中の形状は変更していません。',error=str(exc))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job-directory',type=Path,required=True)
    run(parser.parse_args().job_directory.resolve())
