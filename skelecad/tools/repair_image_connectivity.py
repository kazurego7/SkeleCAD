"""Publish a verified repair with original files and current marker edits retained."""
import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
import trimesh
from workflow_store import PROJECT, ACTIVE, now, process_identity, write_json
from workflow_symmetry_worker import atomic_copy

sys.path.insert(0, str(PROJECT/'src'))
from workflow_connectivity import repair_connectivity
from workflow_debris import remove_isolated_specks


def repair_job(directory):
    state_path = directory/'state.json'; manifest_path = directory/'manifest.json'
    before = json.loads(state_path.read_text(encoding='utf-8'))
    if before['stage'] in ACTIVE | {'queued', 'paused'}:
        raise ValueError('処理中のモデルは修復できません。')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = directory/'appearance.stl'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != manifest['geometry']['sha256']:
        raise ValueError('元形状の照合に失敗しました。')
    revision = uuid.uuid4().hex
    work = directory/'connectivity'/revision; work.mkdir(parents=True)
    backup = work/'original'; backup.mkdir()
    for name in ('appearance.stl','manifest.json','state.json','joint_candidates.json'):
        if (directory/name).exists(): shutil.copy2(directory/name, backup/name)
    write_json(backup/'hashes.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.iterdir()})
    active = dict(before, stage='analysing', operation='connectivity', pid=os.getpid(),
                  process_identity=process_identity(os.getpid()), updated_at=now(), message='分離した接続部を修復しています')
    write_json(state_path, active)
    try:
        parameters = json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))
        cfg = parameters['image_workflow']['connectivity_repair']
        mesh = trimesh.load(source, force='mesh')
        symmetry = manifest.get('appearance_symmetry', {})
        if symmetry.get('active'):
            from workflow_symmetry import symmetrize_yz
            original_dir = directory/'symmetry'/'original'
            record = json.loads((original_dir/'record.json').read_text(encoding='utf-8'))
            original_file = original_dir/'appearance.stl'
            if hashlib.sha256(original_file.read_bytes()).hexdigest() != record['appearance_sha256']:
                raise ValueError('左右対称化前の元形状を照合できません。')
            mesh = symmetrize_yz(trimesh.load(original_file,force='mesh'), symmetry['source_side'])
        mesh, speck_report = remove_isolated_specks(mesh, parameters['image_workflow']['debris_cleanup'])
        mesh.export(work/'before_connectivity.stl')
        mesh = trimesh.load(work/'before_connectivity.stl',force='mesh')
        result, report = repair_connectivity(mesh, cfg, bool(symmetry.get('active')))
        if not report.get('fully_connected'):
            raise ValueError('修復範囲を超える分離があります。元モデルを保持します。')
        candidate = work/'appearance.stl'; result.export(candidate)
        report.update(source_sha256=hashlib.sha256((work/'before_connectivity.stl').read_bytes()).hexdigest(),
                      previous_appearance_sha256=digest)
        write_json(work/'repair_report.json', report)
        geometry = copy.deepcopy(manifest['geometry'])
        geometry['isolated_speck_cleanup'] = speck_report
        geometry.update(connectivity_repair=report,vertices=len(result.vertices),faces=len(result.faces),
                        watertight=bool(result.is_watertight),winding_consistent=bool(result.is_winding_consistent),
                        extents_mm=result.extents.tolist(),sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())
        base = f'../api/jobs/{before["id"]}/files/'
        revised = copy.deepcopy(manifest)
        revised['limitations'] = [item for item in revised.get('limitations', []) if not item.startswith('接続修復の範囲を超える分離')]
        from workflow_geometry import analyse
        detector = before['settings'].get('joint_detection') or parameters['image_workflow']['joint_detection']
        detection = analyse(candidate, work/'joint_candidates.json', detector)
        revised['joint_candidates'] = detection['candidates']
        for key in ('partition_review','mechanical_review','machining','prints','review','print_release'):
            revised.pop(key, None)
        revised.update(geometry=geometry,stage='appearance_review',joints=[],print_ready=False,
                       partition_preview=None,branch_graph=None,connectivity_revision=revision,
                       parts=[{'name':'appearance','label':'接続修復した外観','color':'#cbb98e',
                               'path':base+'appearance.stl','sha256':geometry['sha256']}])
        state = copy.deepcopy(before)
        for key in ('error','partition_revision','mechanical_revision','prints','review_approval',
                    'failed_marker_numbers','failed_marker_names','failed_marker_locations'):
            state.pop(key, None)
        state.update(stage='appearance_ready',operation='connectivity',updated_at=now(),
                     manifest=base+'manifest.json',preview_part_count=1,message='分割位置を指定できます。')
        state['settings']['connectivity_repair'] = cfg
        write_json(work/'manifest.json', revised)
        if state.get('selected_markers'):
            state['source_manifest_sha256'] = hashlib.sha256((work/'manifest.json').read_bytes()).hexdigest()
            write_json(work/'state.json',state)
            from workflow_partition_worker import run
            run(work)
            state = json.loads((work/'state.json').read_text(encoding='utf-8'))
            if state['stage'] != 'appearance_ready':
                raise ValueError(state.get('error','修復後の分割確認に失敗しました。'))
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError('修復中に元形状が変更されました。')
        for path in work.glob('preview_*.stl'): atomic_copy(path,directory/path.name)
        if (work/'partition').exists(): shutil.copytree(work/'partition',directory/'partition',dirs_exist_ok=True)
        atomic_copy(work/'joint_candidates.json', directory/'joint_candidates.json')
        atomic_copy(candidate,source); atomic_copy(work/'manifest.json',manifest_path)
        state.update(manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                     connectivity_revision=revision,updated_at=now(),
                     message='分離した接続部を修復しました。'+state.get('message',''))
        write_json(state_path,state)
        from workflow_symmetry_states import save
        save(directory,state)
        print(json.dumps({'job':before['id'],'report':report,'parts':state['preview_part_count']}))
    except Exception:
        for name in ('appearance.stl','manifest.json','state.json','joint_candidates.json'):
            if (backup/name).exists(): atomic_copy(backup/name,directory/name)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--job-directory',type=Path,required=True)
    parser.add_argument('--refresh-partition',action='store_true')
    args=parser.parse_args(); directory=args.job_directory.resolve()
    if args.refresh_partition:
        state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
        if state['stage'] in ACTIVE | {'queued','paused'}:raise ValueError('処理中のモデルは更新できません。')
        state['source_manifest_sha256']=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        write_json(directory/'state.json',state)
        from workflow_partition_worker import run
        run(directory)
        state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
        if state['stage']!='appearance_ready':raise ValueError(state.get('error','分割を更新できません。'))
        print(json.dumps({'job':state['id'],'parts':state['preview_part_count']}))
    else:
        repair_job(directory)
