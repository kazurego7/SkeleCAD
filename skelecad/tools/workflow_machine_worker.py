"""Publish only a validated mechanical revision. Never overwrite the inference."""
import argparse
import hashlib
import json
import os
import traceback
from pathlib import Path
from workflow_store import now,process_identity,write_json


def run(directory):
    path=directory/'state.json';state=json.loads(path.read_text(encoding='utf-8'))
    def update(**fields):
        state.update(updated_at=now(),**fields);write_json(path,state)
    update(stage='machining',message='関節周囲の加工・丸め・閉じた部品の検証をしています',
           pid=os.getpid(),process_identity=process_identity(os.getpid()))
    try:
        from machine_image_job import machine
        out=machine(directory,state['selected_joints'])
        manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        if manifest['stage']!='mechanical_review':raise ValueError('Mechanical validation incomplete')
        base=f'../api/jobs/{state["id"]}/files/r_{out.name}'
        for part in manifest['parts']:part['path']=base+'_'+part['name']+'.stl'
        write_json(out/'manifest.json',manifest)
        digest=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()
        revision_status=json.loads((out/'status.json').read_text(encoding='utf-8'))
        revision_status['manifest_sha256']=digest;write_json(out/'status.json',revision_status)
        for key in ('error','failed_marker_numbers','failed_marker_names','failed_marker_locations'):state.pop(key,None)
        update(stage='mechanical_review',message=f'{len(manifest["parts"])}部品・{len(manifest["joints"])}関節。ドラッグで可動を確認できます。保持力・印刷準備は未検証です。',
               manifest=base+'.json',manifest_sha256=digest,mechanical_revision=out.name)
    except Exception as exc:
        traceback.print_exc()
        fields={'stage':'machining_failed','message':'ジョイント加工を完了できませんでした。元の分割候補は保持しています。','error':str(exc)}
        numbers=getattr(exc,'marker_numbers',None);names=getattr(exc,'marker_names',None);locations=getattr(exc,'marker_locations',None)
        if numbers:fields['failed_marker_numbers']=numbers
        if names:fields['failed_marker_names']=names
        if locations:fields['failed_marker_locations']=locations
        update(**fields)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job-directory',type=Path,required=True)
    run(parser.parse_args().job_directory.resolve())
