"""Create an immutable marker-constrained partition preview from the source mesh."""
import argparse
import copy
import hashlib
import json
import os
import sys
import traceback
import uuid
from pathlib import Path

import trimesh

from workflow_store import now,process_identity,write_json
from workflow_joint_rules import minimum_joint_spacing

PROJECT=Path(__file__).resolve().parents[1]


def run(directory):
    state_path=directory/'state.json';state=json.loads(state_path.read_text(encoding='utf-8'))
    def update(**fields):state.update(updated_at=now(),**fields);write_json(state_path,state)
    update(stage='partitioning',message='指定位置だけを使って分割プレビューを再計算しています',pid=os.getpid(),process_identity=process_identity(os.getpid()))
    try:
        source=directory/'appearance.stl';manifest_path=directory/'manifest.json'
        source_manifest=manifest_path.read_bytes()
        if hashlib.sha256(source_manifest).hexdigest()!=state['source_manifest_sha256']:raise ValueError('分割元の表示モデルが変更されています。')
        manifest=json.loads(source_manifest);mesh=trimesh.load(source,force='mesh',process=True)
        if not mesh.is_volume:raise ValueError('分割元が閉じた立体ではありません。')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=manifest['geometry']['sha256']:raise ValueError('分割元の形状照合に失敗しました。')
        params=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']['joint_detection']
        markers=copy.deepcopy(state['selected_markers'])
        sys.path.insert(0,str(PROJECT/'src'))
        from workflow_geometry import infer_branches,partition_preview
        branches=infer_branches(mesh,markers,params)
        accepted=[m for m in markers if m.get('classification')=='two_part_junction']
        rejected=[m for m in markers if m.get('classification')!='two_part_junction']
        for marker in accepted:marker['status']='user_selected'
        for marker in rejected:marker['status']='rejected_not_boundary'
        if not accepted:raise ValueError('選択位置のどこにも、2領域を分ける境界を作れません。範囲を広げるか、細い接続部に移してください。')
        revision=uuid.uuid4().hex;review_dir=directory/'partition'/revision;review_dir.mkdir(parents=True)
        preview=partition_preview(mesh,markers,branches,params,directory,filename_prefix='preview_'+revision)
        if not preview or len(preview['parts'])<2:raise ValueError('マーカー以外を結合した分割プレビューを作れません。')
        base=f'../api/jobs/{state["id"]}/files/'
        for part in preview['parts']:part['path']=base+part['filename']
        project_parameters=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))
        controls=dict(manifest.get('partition_controls',{}));controls['minimum_joint_center_spacing_mm']=minimum_joint_spacing(project_parameters)
        result=copy.deepcopy(manifest);result.update(stage='partition_preview',parts=preview['parts'],partition_preview=preview,
            joint_candidates=markers,branch_graph=branches,joints=[],print_ready=False,
            partition_controls=controls,
            partition_review={'revision':revision,'source_manifest_sha256':state['source_manifest_sha256'],'marker_count':len(accepted),
                              'rejected_markers':[m['name'] for m in rejected],
                              'constraint':'only marker regions may create part boundaries','provider':manifest.get('part_segmentation',{}).get('provider','geometry_fallback')})
        write_json(review_dir/'source_manifest.json',manifest);write_json(review_dir/'markers.json',markers);write_json(review_dir/'manifest.json',result)
        write_json(manifest_path,result);digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        skipped=f' {len(rejected)}個は境界にならないため灰色に戻しました。' if rejected else ''
        state.pop('error',None)
        update(stage='appearance_ready',message=f'{len(accepted)}個の指定位置だけで{len(preview["parts"])}パーツに仮分割しました。指定外は結合されています。'+skipped,
               manifest=base+'manifest.json',manifest_sha256=digest,preview_part_count=len(preview['parts']),partition_revision=revision,
               selected_joints=[m['name'] for m in accepted])
    except Exception as exc:
        traceback.print_exc();update(stage='partition_failed',message='分割プレビューを作れませんでした。元の外観と直前のプレビューは保持しています。',error=str(exc))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job-directory',type=Path,required=True)
    run(parser.parse_args().job_directory.resolve())
