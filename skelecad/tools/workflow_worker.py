"""Background image inference, with per-job provenance and explicit review stages."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

from workflow_store import PROJECT, WORKSPACE, now, process_identity, write_json
from runtime_paths import python_path


def prepare_image(source, output):
    """Keep supplied alpha; otherwise use color-independent border-seeded GrabCut.

    This is an initial mask, not a semantic guarantee. Persist it for visual review.
    Do not discard smaller foreground components or select a dinosaur-specific hue.
    """
    import cv2
    import numpy as np
    from PIL import Image

    image = np.asarray(Image.open(source).convert('RGBA')).copy()
    if np.count_nonzero(image[:, :, 3] > 127) < image.shape[0] * image.shape[1] * .01:
        raise ValueError('画像がほぼ透明です。モデルが写った画像を選んでください。')
    if np.any(image[:, :, 3] < 250):
        method = 'supplied_alpha'
    else:
        rgb = image[:, :, :3].copy()
        height, width = rgb.shape[:2]
        border = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1])).astype(float)
        reference = np.median(border, axis=0)
        deviation = np.linalg.norm(border - reference, axis=1)
        # Busy/photographic border: keep all content for review rather than erase anatomy.
        if np.percentile(deviation, 90) > 45:
            method = 'unmasked_complex_background'
        else:
            distance = np.linalg.norm(rgb.astype(float) - reference, axis=2)
            threshold = max(18., float(np.percentile(deviation, 95)) + 8.)
            mask = np.where(distance > threshold, cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype('uint8')
            mask[0, :] = mask[-1, :] = mask[:, 0] = mask[:, -1] = cv2.GC_BGD
            if np.count_nonzero(mask == cv2.GC_PR_FGD) < width * height * .01:
                raise ValueError('背景とモデルを区別できません。背景が単純な画像か透過PNGを使ってください。')
            cv2.setRNGSeed(3407)
            cv2.grabCut(rgb, mask, None, np.zeros((1, 65)), np.zeros((1, 65)), 5, cv2.GC_INIT_WITH_MASK)
            alpha = np.isin(mask, [cv2.GC_FGD, cv2.GC_PR_FGD]).astype('uint8') * 255
            coverage = np.count_nonzero(alpha) / (width * height)
            if not .01 < coverage < .98:
                raise ValueError('背景除去を確認できません。透過PNGでアップロードしてください。')
            image[:, :, 3] = alpha
            method = 'border_seeded_grabcut'
    Image.fromarray(image).save(output)
    return {'method': method, 'requires_visual_review': True,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def normalize_mesh(source, output, length_mm, cleanup=None):
    import numpy as np
    import trimesh
    mesh = trimesh.load(source, force='mesh', process=True)
    if not len(mesh.faces) or not np.isfinite(mesh.vertices).all() or max(mesh.extents) <= 0:
        raise ValueError('3D生成結果に有効な形状がありません。')
    input_faces=len(mesh.faces)
    # Hunyuan marching cubes occasionally emits exactly collapsed triangles.
    # Removing zero-area faces changes no surface.
    mesh.update_faces(mesh.nondegenerate_faces(height=1e-10))
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    surface_faces=len(mesh.faces)
    cleanup=cleanup or json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']['debris_cleanup']
    components=list(mesh.split(only_watertight=False));largest=max(components,key=lambda item:item.area)
    minimum_faces=int(cleanup['minimum_component_faces']);minimum_area=float(mesh.area)*float(cleanup['minimum_component_area_ratio'])
    kept=[];removed=[]
    for component in components:
        if component is largest or len(component.faces)>=minimum_faces or component.area>=minimum_area:kept.append(component)
        else:removed.append(component)
    if not kept:raise ValueError('3D生成結果の微小片除去で形状が残りません。')
    if removed:
        mesh=trimesh.util.concatenate(kept);mesh.remove_unreferenced_vertices()
    # Debris must not enlarge the bounds and make the actual subject scale down.
    original_extents = mesh.extents.copy();scale=float(length_mm/max(original_extents))
    removed_area=float(sum(item.area for item in removed))*scale**2
    removed_volume=float(sum(abs(item.volume) for item in removed))*scale**3
    mesh.apply_translation(-mesh.bounds.mean(axis=0));mesh.apply_scale(scale)
    # Hunyuan's Y-up space -> the existing viewer/printing Z-up space, front to -Y.
    rotation=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]],dtype=float)
    mesh.apply_transform(rotation)
    mesh.export(output)
    return {'vertices': len(mesh.vertices), 'faces': len(mesh.faces), 'removed_degenerate_or_duplicate_faces':input_faces-surface_faces,
            'debris_cleanup':{'input_components':len(components),'kept_components':len(kept),'removed_components':len(removed),
                              'removed_faces':int(sum(len(item.faces) for item in removed)),'removed_area_mm2':removed_area,
                              'removed_volume_mm3':removed_volume,
                              'minimum_component_faces':minimum_faces,'minimum_component_area_mm2':minimum_area*scale**2},
            'watertight': bool(mesh.is_watertight), 'winding_consistent': bool(mesh.is_winding_consistent),
            'extents_mm': mesh.extents.tolist(), 'source_to_viewer_rotation':rotation.tolist(),
            'scale': scale,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def run(directory, analyse_existing=False):
    state_path = directory / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    if analyse_existing:
        if state['stage']!='appearance_ready':
            raise ValueError('Only a completed appearance job can be re-analysed')
        report=json.loads((directory/'inference.json').read_text(encoding='utf-8'))
        if report['output_sha256']!=hashlib.sha256((directory/'inference.glb').read_bytes()).hexdigest() or report['source_original_sha256']!=state['source_sha256']:
            raise ValueError('Inference/source provenance mismatch')
    def update(stage, message, **extra):
        state.update(stage=stage, message=message, updated_at=now(), **extra)
        write_json(state_path, state)
    try:
        update('preparing', '画像の背景と向きを整理しています', pid=os.getpid(),
               process_identity=process_identity(os.getpid()))
        preprocessing = prepare_image(directory / 'source.png', directory / 'input.png')
        write_json(directory / 'preprocessing.json', preprocessing)
        if not analyse_existing:
            update('generating', '画像から3D形状を生成しています（数分かかります）')
        settings = state['settings']
        env = dict(os.environ, HF_HOME=str(WORKSPACE / '.tools/cache/huggingface'),
                   PYTHONUTF8='1', PYTHONUNBUFFERED='1')
        # Running inference in a child frees GPU memory before geometry analysis.
        command = [str(python_path(WORKSPACE, inference=True)), str(PROJECT / 'src/generate_hunyuan_shape.py'),
                   '--input', str(directory / 'input.png'), '--output', str(directory / 'inference.glb'),
                   '--source-original', str(directory / 'source_original.bin'),
                   '--hunyuan-root', str(WORKSPACE / '.tools/Hunyuan3D-2.1'),
                   '--seed', str(settings['seed']), '--steps', str(settings['steps']),
                   '--resolution', str(settings['octree_resolution']),
                   '--decoder', str(settings.get('inference_decoder', 'vanilla')),
                   '--num-chunks', str(settings.get('num_chunks', 8000))]
        if not analyse_existing:
            with (directory / 'inference.log').open('ab') as log:
                subprocess.run(command, env=env, check=True, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        update('analysing', '生成形状とサイズを確認しています')
        if (directory/'appearance.stl').exists():
            import shutil
            old_digest=hashlib.sha256((directory/'appearance.stl').read_bytes()).hexdigest()
            backup=directory/'history'/old_digest;backup.mkdir(parents=True,exist_ok=True)
            for filename in ('appearance.stl','manifest.json'):
                if (directory/filename).exists() and not (backup/filename).exists():shutil.copy2(directory/filename,backup/filename)
        cleanup=settings.get('debris_cleanup') or json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']['debris_cleanup']
        report = normalize_mesh(directory / 'inference.glb', directory / 'appearance.stl', state['target_length_mm'],cleanup)
        sys.path.insert(0,str(PROJECT/'src'))
        from workflow_geometry import analyse
        detector=settings.get('joint_detection') or json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']['joint_detection']
        candidates=analyse(directory/'appearance.stl',directory/'joint_candidates.json',detector)
        base = f"../api/jobs/{state['id']}/files/"
        preview=candidates['partition_preview']
        parts=[{**p,'path':base+p['filename']} for p in preview['parts']] if preview else [{'name':'appearance','label':'生成された外観','color':'#cbb98e','path':base+'appearance.stl','sha256':report['sha256']}]
        project_parameters=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))
        from workflow_joint_rules import minimum_joint_spacing
        partition_controls=dict(settings.get('partition_review',{}))
        partition_controls['joint_ball_diameter_mm']=float(project_parameters['joint']['ball_diameter_mm'])
        partition_controls['minimum_joint_center_spacing_mm']=minimum_joint_spacing(project_parameters)
        manifest = {'schema_version': 1, 'id': state['id'], 'name': state['name'],
                    'stage': 'partition_preview' if preview else 'appearance_review', 'source_sha256': state['source_sha256'],
                    'target_length_mm': state['target_length_mm'], 'preprocessing': preprocessing,
                    'parts':parts,'partition_preview':preview,
                    'joints': [], 'joint_candidates':candidates['candidates'], 'branch_graph':candidates['branch_graph'], 'joint_detection':detector,
                    'geometry': report, 'print_ready': False,
                    'partition_controls': partition_controls,
                    'limitations': ['外観のみ。パーツ分割・精密ジョイント加工・可動確認・印刷検証は未完了。']}
        write_json(directory / 'manifest.json', manifest)
        message=f"{len(parts)}パーツの分割候補を色分け。可動ジョイント加工・印刷準備は未完了です。" if preview else f"外観の生成完了。球状の候補{len(candidates['candidates'])}箇所。パーツ分割・ジョイント加工は未完了です。"
        update('appearance_ready', message,
               manifest=base + 'manifest.json',manifest_sha256=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),preview_part_count=len(parts))
    except Exception as exc:
        traceback.print_exc()
        message = str(exc) if isinstance(exc, ValueError) else '3D生成処理に失敗しました。元画像とログは保存されています。'
        update('failed', message, error=type(exc).__name__)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-directory', type=Path, required=True)
    parser.add_argument('--analyse-existing',action='store_true')
    args=parser.parse_args()
    run(args.job_directory.resolve(),args.analyse_existing)
