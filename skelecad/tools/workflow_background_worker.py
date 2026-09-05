"""Speculative downstream work on an immutable private snapshot; no user-state writes."""
import argparse
import hashlib
import json
import traceback
from pathlib import Path
from workflow_store import write_json


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(directory):
    state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    joints=state.get('selected_joints')
    if joints is None:joints=[c['name'] for c in manifest.get('joint_candidates',[]) if c.get('classification')=='two_part_junction']
    project=Path(__file__).resolve().parents[1]
    value={'manifest':digest(directory/'manifest.json'),
           'appearance':digest(directory/'appearance.stl'),
           'markers':state.get('selected_markers'),'joints':sorted(joints),
           'settings':digest(project/'config/parameters.json'),
           'toolchain':digest(project/'config/toolchain.json'),
           'code':{str(p.relative_to(project)):digest(p) for folder in ('src','tools')
                   for p in sorted((project/folder).glob('*.py'))}}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def run(snapshot):
    control=json.loads((snapshot.parent/'request.json').read_text(encoding='utf-8'))
    original=Path(control['original']);output=snapshot.parent/'result.json'
    def current():
        try:return source_identity(original)==control['identity']
        except (OSError,ValueError):return False
    last_preview=None
    def report(**fields):
        if last_preview:fields.setdefault('preview',last_preview)
        write_json(output,{'identity':control['identity'],**fields})
    def progress(preview):
        nonlocal last_preview
        if not current():raise InterruptedError('Newer input superseded preview')
        last_preview=preview;report(stage='working')
    directory=None
    try:
        if not current():report(stage='superseded');return
        from machine_image_job import machine, changed_joint_names
        state=json.loads((snapshot/'state.json').read_text(encoding='utf-8'))
        revision=control.get('mechanical_revision')
        directory=snapshot/'machining'/revision if revision else machine(snapshot,state.get('selected_joints'),cancelled=lambda:not current(),priority_markers=changed_joint_names(original),progress=progress)
        if not current():report(stage='superseded');return
        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        for part in manifest['parts']:
            part['path']=f'../api/jobs/{original.name}/files/r_{directory.name}_{part["name"]}.stl'
        write_json(directory/'manifest.json',manifest)
        status=json.loads((directory/'status.json').read_text(encoding='utf-8'))
        status['manifest_sha256']=digest(directory/'manifest.json');write_json(directory/'status.json',status)
        report(stage='mechanical_ready',revision=directory.name,manifest_sha256=digest(directory/'manifest.json'))
        from prepare_workflow_project import run as prepare_print
        prepare_print(directory,verification_run=True)
        if not current():report(stage='superseded');return
        report(stage='ready',revision=directory.name,manifest_sha256=digest(directory/'manifest.json'))
    except Exception as exc:
        if not current():report(stage='superseded');return
        traceback.print_exc()
        if directory and (directory/'manifest.json').is_file():
            report(stage='print_failed',revision=directory.name,
                   manifest_sha256=digest(directory/'manifest.json'),error=str(exc))
        else:report(stage='failed',error=str(exc),failed_marker_locations=getattr(exc,'marker_locations',[]))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',type=Path,required=True)
    run(parser.parse_args().snapshot.resolve())
